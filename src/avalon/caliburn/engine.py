"""Caliburn view engine — resolve, compile, cache, render."""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from avalon.caliburn.compiler import DirectiveHandler, RenderFn, compile_template
from avalon.orm.inflector import studly

ComposerCallback = Callable[[dict[str, Any]], None]


class ViewNotFoundError(LookupError):
    """Raised when a template name cannot be resolved on disk."""


def _normalize_view_patterns(views: str | Sequence[str]) -> list[str]:
    if isinstance(views, str):
        return [views]
    return list(views)


def _view_matches(name: str, pattern: str) -> bool:
    """Match a view name against ``*``, ``profile.*``, or an exact name."""
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        root = pattern[:-2]
        return name == root or name.startswith(root + ".")
    if pattern.endswith("*"):
        return name.startswith(pattern[:-1])
    return name == pattern


class Engine:
    """Compile-ahead view engine with mtime-based cache invalidation."""

    def __init__(
        self,
        *,
        paths: list[Path] | None = None,
        extension: str = ".cal.html",
        cache_enabled: bool = True,
        component_namespaces: list[str] | None = None,
    ) -> None:
        self.paths = [Path(p) for p in (paths or [])]
        self.extension = extension
        self.cache_enabled = cache_enabled
        self.component_namespaces = list(
            component_namespaces or ["app.view.components"]
        )
        self._cache: dict[str, tuple[float, RenderFn]] = {}
        self._directives: dict[str, DirectiveHandler] = {}
        self._composers: list[tuple[list[str], ComposerCallback]] = []
        self._creators: list[tuple[list[str], ComposerCallback]] = []
        self._created: set[str] = set()
        self._fragments: dict[str, str] = {}

    def add_path(self, path: Path | str) -> None:
        self.paths.append(Path(path))

    def find(self, name: str) -> Path:
        """Resolve a dotted/slash view name to a template file."""
        if name.endswith(self.extension):
            relative = name
        else:
            relative = f"{name.replace('.', '/')}{self.extension}"
        for root in self.paths:
            candidate = root / relative
            if candidate.is_file():
                return candidate
        searched = ", ".join(str(p) for p in self.paths) or "(no paths)"
        raise ViewNotFoundError(f"View [{name}] not found in: {searched}")

    def exists(self, name: str) -> bool:
        """Return whether a view name resolves on disk."""
        try:
            self.find(name)
            return True
        except ViewNotFoundError:
            return False

    def directive(self, name: str, handler: DirectiveHandler) -> None:
        """Register a custom ``@name`` directive handler ``(expr) -> python``."""
        self._directives[name] = handler
        self.clear_cache()

    def composer(
        self,
        views: str | Sequence[str],
        callback: ComposerCallback,
    ) -> None:
        """Run ``callback(context)`` before every matching view render."""
        self._composers.append((_normalize_view_patterns(views), callback))

    def creator(
        self,
        views: str | Sequence[str],
        callback: ComposerCallback,
    ) -> None:
        """Run ``callback(context)`` once per matching view name per engine life."""
        self._creators.append((_normalize_view_patterns(views), callback))

    def remember_fragment(self, key: str, factory: Callable[[], str]) -> str:
        """Return a cached fragment string, compiling via ``factory`` on miss."""
        cached = self._fragments.get(key)
        if cached is not None:
            return cached
        html = factory()
        self._fragments[key] = html
        return html

    def render(self, name: str, context: dict[str, Any] | None = None) -> str:
        ctx = dict(context or {})
        self._inject_helpers(ctx)
        self._run_creators(name, ctx)
        self._run_composers(name, ctx)
        render_fn = self._load(name)
        return render_fn(ctx, self)

    def render_component(
        self,
        name: str,
        context: dict[str, Any],
        slot: Any,
        slots: dict[str, Any],
        attrs: dict[str, Any] | None = None,
    ) -> str:
        """Render a class-based or anonymous component with slots + attributes."""
        from avalon.caliburn.attributes import AttributeBag
        from avalon.caliburn.component import Component
        from avalon.caliburn.escape import DeferredHtml

        attrs = dict(attrs or {})
        parent_data = dict(context.get("__component_data") or {})
        cls = self.resolve_component_class(name)
        if cls is not None and issubclass(cls, Component):
            instance = self._instantiate_component(cls, attrs)
            view_name = instance.render()
            component_data = dict(instance.data())
            leftover = {
                key: value
                for key, value in attrs.items()
                if key not in component_data
            }
            leftover.update(instance.attribute_data())
            bag = AttributeBag({**component_data, **leftover})
        else:
            view_name = name if name.startswith("components.") else f"components.{name}"
            component_data = dict(attrs)
            bag = AttributeBag(attrs)

        # Shared mutable scope so @props can enrich data before nested slots run.
        scope = {**component_data}
        ctx = dict(context)
        ctx["attributes"] = bag
        for key, value in component_data.items():
            ctx[key] = value
        ctx["__aware_parent"] = parent_data
        ctx["__component_data"] = scope
        ctx["__passed_attrs"] = set(attrs.keys()) | set(component_data.keys())

        def _invoke(factory: Any) -> str:
            if not callable(factory):
                return str(factory or "")
            try:
                return str(factory(ctx) or "")
            except TypeError:
                return str(factory() or "")

        ctx["slot"] = DeferredHtml(lambda: _invoke(slot))
        resolved: dict[str, Any] = {}
        for key, factory in (slots or {}).items():
            deferred = DeferredHtml(lambda f=factory: _invoke(f))
            resolved[key] = deferred
            ctx[key] = deferred
        ctx["slots"] = resolved

        html = self.render(view_name, ctx)
        return html

    def resolve_component_class(self, name: str) -> type | None:
        """Map ``alert`` / ``forms.input`` to ``app.view.components…`` classes."""
        from avalon.caliburn.component import Component

        dotted = name.replace("-", "_").replace("/", ".")
        parts = [p for p in dotted.split(".") if p]
        if not parts:
            return None
        class_name = studly(parts[-1])
        module_tail = ".".join(parts)
        for ns in self.component_namespaces:
            module_name = f"{ns}.{module_tail}"
            try:
                module = importlib.import_module(module_name)
            except ImportError:
                continue
            candidate = getattr(module, class_name, None)
            if isinstance(candidate, type) and issubclass(candidate, Component):
                return candidate
        return None

    @staticmethod
    def _instantiate_component(cls: type, attrs: dict[str, Any]) -> Any:
        from avalon.caliburn.component import Component

        try:
            signature = inspect.signature(cls.__init__)
        except (TypeError, ValueError):
            return cls(**attrs)

        kwargs: dict[str, Any] = {}
        accepts_var_kw = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in signature.parameters.values()
        )
        for key, value in attrs.items():
            if key in signature.parameters or accepts_var_kw:
                kwargs[key] = value
        instance = cls(**kwargs)
        assert isinstance(instance, Component)
        leftovers = {k: v for k, v in attrs.items() if k not in kwargs}
        if leftovers:
            instance.with_attributes(leftovers)
        return instance

    @staticmethod
    def _inject_helpers(ctx: dict[str, Any]) -> None:
        """Make common Avalon helpers available inside templates."""
        if "config" not in ctx:
            from avalon.config import config

            ctx["config"] = config
        if "url" not in ctx:
            from avalon.routing.url import url

            ctx["url"] = url
        if "asset" not in ctx:
            from avalon.routing.url import asset

            ctx["asset"] = asset
        if "e" not in ctx:
            from avalon.caliburn.escape import e

            ctx["e"] = e
        if "csrf_field" not in ctx:
            from avalon.caliburn.helpers import csrf_field, method_field

            ctx["csrf_field"] = csrf_field
            ctx["method_field"] = method_field
        if "old" not in ctx:
            from avalon.session.helpers import old

            ctx["old"] = old
        if "__" not in ctx:
            from avalon.translation import __, trans_choice

            ctx["__"] = __
            ctx["trans"] = __
            ctx["trans_choice"] = trans_choice
        if "__stacks" not in ctx or ctx["__stacks"] is None:
            from avalon.caliburn.stacks import StackBag

            ctx["__stacks"] = StackBag()

    def _patterns_match(self, name: str, patterns: list[str]) -> bool:
        return any(_view_matches(name, pattern) for pattern in patterns)

    def _run_creators(self, name: str, ctx: dict[str, Any]) -> None:
        if name in self._created:
            return
        ran = False
        for patterns, callback in self._creators:
            if self._patterns_match(name, patterns):
                callback(ctx)
                ran = True
        if ran:
            self._created.add(name)

    def _run_composers(self, name: str, ctx: dict[str, Any]) -> None:
        for patterns, callback in self._composers:
            if self._patterns_match(name, patterns):
                callback(ctx)

    def _load(self, name: str) -> RenderFn:
        path = self.find(name)
        key = str(path.resolve())
        mtime = path.stat().st_mtime
        if self.cache_enabled:
            cached = self._cache.get(key)
            if cached is not None and cached[0] == mtime:
                return cached[1]
        source = path.read_text(encoding="utf-8")
        render_fn = compile_template(source, name=key, directives=self._directives)
        if self.cache_enabled:
            self._cache[key] = (mtime, render_fn)
        return render_fn

    def clear_cache(self) -> None:
        self._cache.clear()
        self._fragments.clear()
        self._created.clear()

    def cache_views(self) -> int:
        """Compile all ``*.cal.html`` templates under configured paths."""
        count = 0
        for root in self.paths:
            if not root.is_dir():
                continue
            for path in sorted(root.rglob(f"*{self.extension}")):
                if not path.is_file():
                    continue
                rel = path.relative_to(root).as_posix()[: -len(self.extension)]
                name = rel.replace("/", ".")
                self._load(name)
                count += 1
        return count

    def warm_cache(self) -> int:
        """Alias for :meth:`cache_views`."""
        return self.cache_views()
