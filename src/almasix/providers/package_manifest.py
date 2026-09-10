"""Discover third-party service providers (Laravel ``PackageManifest``)."""

from __future__ import annotations

import importlib.metadata
from typing import Any

#: Entry-point group packages use to advertise providers.
ENTRY_POINT_GROUP = "almasix.providers"


class PackageManifest:
    """Resolve provider class paths from installed package metadata.

    Packages declare providers via the ``almasix.providers`` entry-point
    group in ``pyproject.toml``::

        [project.entry-points."almasix.providers"]
        courier = "courier.provider:CourierServiceProvider"

    Apps can skip discovery entirely (``app.skip_provider_discovery``) or
    exclude specific packages by distribution name (``app.dont_discover``),
    matching Laravel's ``dont-discover`` list.
    """

    def __init__(self, *, group: str = ENTRY_POINT_GROUP) -> None:
        self.group = group

    def providers(self, dont_discover: list[str] | None = None) -> list[str]:
        """Dotted ``module.Class`` paths for every discovered provider.

        ``dont_discover`` is matched against the distribution name that
        owns the entry point (e.g. ``almasix-courier``), case-insensitive.
        """
        skip = {name.lower() for name in (dont_discover or [])}
        found: list[str] = []
        seen: set[str] = set()
        for ep in self._entry_points():
            dist = (getattr(ep, "dist", None) and ep.dist.name) or ""
            if dist.lower() in skip:
                continue
            path = self._provider_path(ep)
            if path and path not in seen:
                seen.add(path)
                found.append(path)
        return found

    def _entry_points(self) -> list[Any]:
        """Entry points for this group's installed packages."""
        try:
            selected = importlib.metadata.entry_points(group=self.group)
        except TypeError:  # pragma: no cover - Python < 3.10 shape
            selected = importlib.metadata.entry_points().get(self.group, [])
        return list(selected)

    @staticmethod
    def _provider_path(ep: Any) -> str | None:
        """Turn ``module:Class`` (or ``module.Class``) into an importable path."""
        raw = getattr(ep, "value", None)
        value = raw if raw is not None else str(ep)
        if not value:
            return None
        if ":" in value:
            module, _, name = value.partition(":")
            return f"{module}.{name}" if module and name else None
        return value
