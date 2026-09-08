"""Base service provider."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from almasix.framework.application import Application


class ServiceProvider:
    #: Every path a provider has offered, as ``provider name -> {source: destination}``.
    _publishes: ClassVar[dict[str, dict[Path, Path]]] = {}

    #: The same paths indexed by tag, so ``--tag`` can cut across providers.
    _publish_groups: ClassVar[dict[str, dict[Path, Path]]] = {}

    def __init__(self, app: Application) -> None:
        self.app = app

    def register(self) -> None:
        """Bind services into the container."""

    def boot(self) -> None:
        """Run after all providers have registered."""

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
    def paths_to_publish(cls, provider: str | None = None, tag: str | None = None) -> dict[Path, Path]:
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
    def forget_publishes(cls) -> None:
        """Drop every declaration, so one test's provider cannot leak into the next."""
        ServiceProvider._publishes.clear()
        ServiceProvider._publish_groups.clear()
