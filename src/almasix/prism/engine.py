"""Prism view engine — resolve, compile, cache, render."""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from almasix.orm.inflector import studly
from almasix.prism.compiler import DirectiveHandler, RenderFn, compile_template

ComposerCallback = Callable[[dict[str, Any]], None]


#: Views rendered while a recorder is installed. `None` — the normal case —
#: means nothing is watching, so rendering costs what it always did.
_renders: list[tuple[str, dict[str, Any]]] | None = None


def record_renders() -> list[tuple[str, dict[str, Any]]]:
    """Start recording `(view name, data)` pairs, for `almasix.testing`."""
    global _renders
    _renders = []
    return _renders


def stop_recording_renders() -> None:
    global _renders
    _renders = None


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
        extension: str = ".prism.html",
        cache_enabled: bool = True,
        component_namespaces: list[str] | None = None,
    ) -> None:
        self.paths = [Path(p) for p in (paths or [])]
        self.extension = extension
        self.cache_enabled = cache_enabled
        self.component_namespaces = list(component_namespaces or ["app.view.components"])
        #: Package view hints — ``namespace -> directory`` for ``ns::view``.
        self.hints: dict[str, Path] = {}
        self._cache: dict[str, tuple[float, RenderFn]] = {}
        self._directives: dict[str, DirectiveHandler] = {}
        self._composers: list[tuple[list[str], ComposerCallback]] = []
        self._creators: list[tuple[list[str], ComposerCallback]] = []
        self._created: set[str] = set()
        self._fragments: dict[str, str] = {}

    def add_path(self, path: Path | str) -> None:
        self.paths.append(Path(path))

    def add_namespace(self, namespace: str, path: Path | str) -> None:
        """Register a package view namespace (Laravel ``loadViewsFrom``).

        After registration, ``view("courier::welcome")`` resolves against
        ``path``, with optional app overrides under
        ``resources/views/vendor/courier/``.
        """
        self.hints[namespace] = Path(path)

    def find(self, name: str) -> Path:
        """Resolve a dotted/slash or ``namespace::name`` view to a template file."""
        if "::" in name:
            return self._find_namespaced(name)
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

    def _find_namespaced(self, name: str) -> Path:
        """Resolve ``namespace::view`` — vendor override first, then the hint."""
        namespace, _, view = name.partition("::")
        if not namespace or not view:
            raise ViewNotFoundError(f"View [{name}] is not a valid namespaced name")
        relative = f"{view.replace('.', '/')}{self.extension}"
        # Published overrides win — same order as Laravel's view finder.
        for root in self.paths:
            vendor = root / "vendor" / namespace / relative
            if vendor.is_file():
                return vendor
        hint = self.hints.get(namespace)
        if hint is not None:
            candidate = Path(hint) / relative
            if candidate.is_file():
                return candidate
        searched = str(hint) if hint is not None else "(no hint)"
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
        if _renders is not None:
            _renders.append((name, dict(context or {})))
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
        from almasix.prism.attributes import AttributeBag
        from almasix.prism.component import Component
        from almasix.prism.escape import DeferredHtml

        attrs = dict(attrs or {})
        parent_data = dict(context.get("__component_data") or {})
        cls = self.resolve_component_class(name)
        if cls is not None and issubclass(cls, Component):
            instance = self._instantiate_component(cls, attrs)
            view_name = instance.render()
            component_data = dict(instance.data())
            leftover = {key: value for key, value in attrs.items() if key not in component_data}
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
        from almasix.prism.component import Component

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
        from almasix.prism.component import Component

        try:
            signature = inspect.signature(cls.__init__)
        except (TypeError, ValueError):
            return cls(**attrs)

        kwargs: dict[str, Any] = {}
        accepts_var_kw = any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()
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
        """Make common Almasix helpers available inside templates."""
        if "config" not in ctx:
            from almasix.config import config

            ctx["config"] = config
        if "url" not in ctx:
            from almasix.routing.url import url

            ctx["url"] = url
        if "asset" not in ctx:
            from almasix.routing.url import asset

            ctx["asset"] = asset
        # Inject each helper only when the view did not pass the same name —
        # otherwise ``{{ action }}`` becomes the ``action()`` controller URL
        # helper and forms POST to ``/<function action at 0x…>``.
        if "route" not in ctx or "signed_route" not in ctx or "action" not in ctx:
            from almasix.routing.url import (
                action,
                route,
                secure_asset,
                secure_url,
                signed_route,
            )

            ctx.setdefault("route", route)
            ctx.setdefault("signed_route", signed_route)
            ctx.setdefault("action", action)
            ctx.setdefault("secure_url", secure_url)
            ctx.setdefault("secure_asset", secure_asset)
        if "route_is" not in ctx:
            from almasix.routing.router import Route

            # `@if(route_is('posts.*'))` is how a nav link marks itself active.
            ctx["route_is"] = Route.is_
            ctx["current_route_name"] = Route.current_route_name
        if "vite" not in ctx:
            from almasix.prism.vite import vite, vite_react_refresh

            ctx["vite"] = vite
            ctx["vite_react_refresh"] = vite_react_refresh
        if "e" not in ctx:
            from almasix.prism.escape import e

            ctx["e"] = e
        if "csrf_field" not in ctx:
            from almasix.prism.helpers import csrf_field, method_field

            ctx["csrf_field"] = csrf_field
            ctx["method_field"] = method_field
        if "old" not in ctx:
            from almasix.session.helpers import old

            ctx["old"] = old
        if "csp_nonce" not in ctx:
            from almasix.http.security import csp_nonce

            ctx["csp_nonce"] = csp_nonce
        if "__" not in ctx:
            from almasix.translation import __, trans_choice

            ctx["__"] = __
            ctx["trans"] = __
            ctx["trans_choice"] = trans_choice
        if "__stacks" not in ctx or ctx["__stacks"] is None:
            from almasix.prism.stacks import StackBag

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
        """Compile all ``*.prism.html`` templates under configured paths and hints."""
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
        for namespace, hint in self.hints.items():
            if not hint.is_dir():
                continue
            for path in sorted(hint.rglob(f"*{self.extension}")):
                if not path.is_file():
                    continue
                rel = path.relative_to(hint).as_posix()[: -len(self.extension)]
                name = f"{namespace}::{rel.replace('/', '.')}"
                self._load(name)
                count += 1
        return count

    def warm_cache(self) -> int:
        """Alias for :meth:`cache_views`."""
        return self.cache_views()
