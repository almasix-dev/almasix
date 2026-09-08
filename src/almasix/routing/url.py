"""URL generation honoring `APP_URL` and `APP_BASE_PATH`.

Apps hosted under a subpath (`/apps/foo`) must never emit root-absolute links,
so every generated URL runs through here. The HTTP kernel mounts the ASGI app
at the same prefix so `smith serve` matches what `url()` emits.
"""

from __future__ import annotations

import re

from almasix.config import config

_ABSOLUTE_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*:)?//")


def _normalize_root(root: str) -> str:
    return root.strip().rstrip("/")


def _normalize_base(base: str) -> str:
    base = base.strip().strip("/")
    return f"/{base}" if base else ""


class UrlGenerator:
    """Builds URLs from a canonical origin plus a public path prefix."""

    def __init__(self, root: str = "", base_path: str = "") -> None:
        self.root = _normalize_root(root)
        self.base_path = _normalize_base(base_path)

    @classmethod
    def from_config(cls) -> UrlGenerator:
        return cls(
            root=str(config("app.url", "") or ""),
            base_path=str(config("app.base_path", "") or ""),
        )

    def to(self, path: str = "/", *, absolute: bool = True) -> str:
        if _ABSOLUTE_RE.match(path):
            return path

        suffix = path.strip()
        suffix = f"/{suffix.lstrip('/')}" if suffix.strip("/") else ""
        full = f"{self.base_path}{suffix}" or "/"
        if not absolute:
            return full
        return f"{self.root}{full}" if self.root else full

    def asset(self, path: str, *, absolute: bool = True) -> str:
        """Public URL for a file under ``public/`` (subpath-aware).

        Default apps ship Vite + Tailwind emitting into ``public/build/``.
        Keep calling ``asset(...)`` for any file under ``public/``.
        """
        return self.to(path, absolute=absolute)


def url(path: str = "/", *, absolute: bool = True) -> str:
    """Generate a URL for `path`, prefixed with `APP_BASE_PATH`."""
    return UrlGenerator.from_config().to(path, absolute=absolute)


def asset(path: str, *, absolute: bool = True) -> str:
    """Generate a URL for a static asset."""
    return UrlGenerator.from_config().asset(path, absolute=absolute)
