"""Inertia middleware — asset version mismatch → 409."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from starlette.responses import Response as StarletteResponse

from almasix.http.middleware import Middleware, NextCall

if TYPE_CHECKING:
    from almasix.http.request import Request


class HandleInertiaRequests(Middleware):
    """Share flash props and enforce ``X-Inertia-Version`` (Laravel middleware)."""

    async def handle(self, request: Request, call_next: NextCall) -> StarletteResponse:
        from inertia.response import Inertia, _is_inertia

        if _is_inertia(request):
            client_version = request.header("X-Inertia-Version")
            if (
                client_version is not None
                and client_version != ""
                and client_version != Inertia.version()
            ):
                parts = urlsplit(request.url)
                url = parts.path or "/"
                if parts.query:
                    url = f"{url}?{parts.query}"
                return StarletteResponse(
                    status_code=409,
                    headers={"X-Inertia-Location": url},
                )

        response = await call_next(request)

        if _is_inertia(request) and isinstance(response, StarletteResponse):
            response.headers.setdefault("X-Inertia", "true")
            response.headers.setdefault("Vary", "X-Inertia")

        return response
