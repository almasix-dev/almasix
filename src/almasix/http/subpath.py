"""Public mount path (`APP_BASE_PATH`) for subpath hosting."""

from __future__ import annotations

from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.routing import Mount, Route


def normalize_base_path(value: str | None) -> str:
    """Return ``/prefix`` or ``\"\"`` when the app is hosted at the site root."""
    base = (value or "").strip().strip("/")
    return f"/{base}" if base else ""


def mount_asgi(app: Any, base_path: str | None) -> Any:
    """Serve ``app`` under ``base_path`` and redirect ``/`` to the mount.

    Route URIs stay unprefixed inside the app; ``url()`` adds the public prefix
    so generated links match what this wrapper serves.
    """
    base = normalize_base_path(base_path)
    if not base:
        return app

    async def redirect_root(_request: Request) -> RedirectResponse:
        return RedirectResponse(url=f"{base}/", status_code=307)

    return Starlette(
        routes=[
            Route("/", endpoint=redirect_root),
            Mount(base, app=app),
        ]
    )
