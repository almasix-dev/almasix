"""Base service provider."""

from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from almasix.framework.application import Application

_MIGRATION_SLUG_RE = re.compile(r"^(?:\d{4}_\d{2}_\d{2}_\d{6}_)?(.+?)(?:\.py(?:\.stub)?)?$")


class ServiceProvider:
    #: Every path a provider has offered, as ``provider name -> {source: destination}``.
    _publishes: ClassVar[dict[str, dict[Path, Path]]] = {}

    #: The same paths indexed by tag, so ``--tag`` can cut across providers.
    _publish_groups: ClassVar[dict[str, dict[Path, Path]]] = {}

    #: Sources declared via ``publishes_migrations`` — rewritten with a fresh
    #: timestamp when ``vendor:publish`` copies them.
    _publish_migrations: ClassVar[set[Path]] = set()

    def __init__(self, app: Application) -> None:
        self.app = app

    def register(self) -> None:
        """Bind services into the container."""

    def boot(self) -> None:
        """Run after all providers have registered."""

    # --- package resources ------------------------------------------------

    def merge_config_from(self, path: str | Path, key: str) -> None:
        """Merge a package config file under ``key`` (Laravel ``mergeConfigFrom``).

        Package defaults fill missing keys; values already present in the
        application's config (published or otherwise) win.
        """
        defaults = self._load_config_file(Path(path))
        if not isinstance(defaults, dict):
            defaults = {}
        if not self.app.config.has(key):
            self.app.config.set(key, defaults)
            return
        existing = self.app.config.get(key)
        if isinstance(existing, dict):
            self.app.config.set(key, {**defaults, **existing})
        # Non-dict existing values are left alone — the app already configured it.

    def load_routes_from(self, path: str | Path) -> None:
        """Execute a package route file (Laravel ``loadRoutesFrom``)."""
        self.app.load_route_file(Path(path))

    def load_views_from(self, path: str | Path, namespace: str) -> None:
        """Register package views as ``namespace::name`` and offer them for publish.

        After this call, ``view("courier::welcome")`` resolves against ``path``.
        Published overrides land in ``resources/views/vendor/{namespace}/``.
        """
        hint = Path(path)
        try:
            from almasix.prism.engine import Engine

            if self.app.container.bound(Engine):
                self.app.make(Engine).add_namespace(namespace, hint)
        except Exception:  # pragma: no cover - soft boot before Prism
            pass

        # Offer the whole views tree under the vendor publish convention.
        destination = self.app.path("resources", "views", "vendor", namespace)
        if hint.is_dir():
            self.publishes({hint: destination}, f"{namespace}-views")

    def load_migrations_from(self, paths: str | Path | Sequence[str | Path]) -> None:
        """Register migration directories so ``smith migrate`` finds them without publishing."""
        from almasix.orm.migration import register_migration_paths

        register_migration_paths(paths)

    def load_translations_from(self, path: str | Path, namespace: str) -> None:
        """Register a translation namespace (Laravel ``loadTranslationsFrom``)."""
        try:
            from almasix.translation.helpers import Lang

            Lang.add_namespace(namespace, path)
        except Exception:  # pragma: no cover - soft boot before translator
            pass

    def publishes_migrations(self, paths: dict[str | Path, str | Path], *tags: str) -> None:
        """Offer migration files for publish; destinations get a fresh timestamp.

        Like ``publishes``, but ``vendor:publish`` rewrites each destination
        filename to ``YYYY_MM_DD_HHMMSS_{slug}.py`` so published migrations
        run after the application's existing ones.
        """
        resolved = {Path(source): Path(destination) for source, destination in paths.items()}
        ServiceProvider._publish_migrations.update(resolved)
        group_tags = tags or ("migrations",)
        self.publishes(resolved, *group_tags)

    def commands(self, command_classes: Sequence[type[Any]]) -> None:
        """Register Command classes on the console kernel when it is available."""
        try:
            from almasix.console.kernel import ConsoleKernel

            kernel = self.app.make(ConsoleKernel)
            for command_cls in command_classes:
                kernel.register(command_cls)
        except Exception:  # pragma: no cover - soft boot before console
            pass

    # --- publishing -----------------------------------------------------

    def publishes(self, paths: dict[str | Path, str | Path], *tags: str) -> None:
        """Offer files for ``smith vendor:publish`` (Laravel ``$this->publishes()``).

        Called from ``boot()``, mapping each file or directory the package
        ships to where it belongs in the application::

            self.publishes({here / "config" / "courier.py": self.app.path("config", "courier.py")}, "courier")

        Nothing is copied here. Declaring a path only makes it publishable;
        the user chooses when, which is the point of the command.
        """
        resolved = {Path(source): Path(destination) for source, destination in paths.items()}
        name = self.provider_name()
        ServiceProvider._publishes.setdefault(name, {}).update(resolved)
        for tag in tags:
            ServiceProvider._publish_groups.setdefault(tag, {}).update(resolved)

    @classmethod
    def provider_name(cls) -> str:
        """The dotted path a ``--provider`` value is matched against."""
        return f"{cls.__module__}.{cls.__qualname__}"

    @classmethod
    def publishable_providers(cls) -> list[str]:
        return sorted(ServiceProvider._publishes)

    @classmethod
    def publishable_tags(cls) -> list[str]:
        return sorted(ServiceProvider._publish_groups)

    @classmethod
    def paths_to_publish(
        cls, provider: str | None = None, tag: str | None = None
    ) -> dict[Path, Path]:
        """The paths matching a provider, a tag, both, or — given neither — all of them."""
        if provider is None and tag is None:
            everything: dict[Path, Path] = {}
            for paths in ServiceProvider._publishes.values():
                everything.update(paths)
            return everything
        by_provider = ServiceProvider._publishes.get(provider or "", {})
        by_tag = ServiceProvider._publish_groups.get(tag or "", {})
        if provider is not None and tag is not None:
            return {source: dest for source, dest in by_provider.items() if source in by_tag}
        return dict(by_provider or by_tag)

    @classmethod
    def is_migration_publish(cls, source: Path) -> bool:
        """Whether ``source`` was declared through ``publishes_migrations``."""
        return Path(source) in ServiceProvider._publish_migrations

    @classmethod
    def migration_publish_destination(cls, source: Path, destination: Path) -> Path:
        """Rewrite a migration destination with a fresh timestamp prefix."""
        stamp = datetime.now(UTC).strftime("%Y_%m_%d_%H%M%S")
        match = _MIGRATION_SLUG_RE.match(destination.name)
        slug = match.group(1) if match else destination.stem
        slug = slug.removesuffix(".py").removesuffix(".stub")
        # Prefer the source slug when the destination is a bare directory entry.
        if not slug or slug == destination.name:
            source_match = _MIGRATION_SLUG_RE.match(source.name)
            slug = source_match.group(1) if source_match else source.stem
            slug = slug.removesuffix(".py").removesuffix(".stub")
        return destination.with_name(f"{stamp}_{slug}.py")

    @classmethod
    def forget_publishes(cls) -> None:
        """Drop every declaration, so one test's provider cannot leak into the next."""
        ServiceProvider._publishes.clear()
        ServiceProvider._publish_groups.clear()
        ServiceProvider._publish_migrations.clear()

    @staticmethod
    def _load_config_file(file: Path) -> Any:
        """Load a ``config = {...}`` module (or top-level non-private names)."""
        module_name = f"almasix_pkg_config_{file.stem}_{abs(hash(file))}"
        spec = importlib.util.spec_from_file_location(module_name, file)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load config file: {file}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(module_name, None)
        if hasattr(module, "config"):
            return module.config
        return {
            name: getattr(module, name)
            for name in dir(module)
            if not name.startswith("_") and name != "env"
        }
