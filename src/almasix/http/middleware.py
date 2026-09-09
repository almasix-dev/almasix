"""HTTP middleware base type."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from starlette.responses import Response as StarletteResponse

if TYPE_CHECKING:
    from almasix.http.request import Request

NextCall = Callable[["Request"], Awaitable[StarletteResponse]]

#: Aliases the framework itself provides, so a route can say `signed` without
#: every application repeating the import. These sit underneath whatever the
#: application aliases, so an app entry of the same name wins — and they apply
#: even to an app that never opened `bootstrap/app.py`.
FRAMEWORK_ALIASES: dict[str, str] = {
    "signed": "almasix.routing.middleware.ValidateSignature",
    "url.defaults": "almasix.routing.middleware.SetUrlDefaults",
}


class Middleware:
    """Laravel-style middleware with ``handle(request, next)``."""

    async def handle(self, request: Request, call_next: NextCall) -> StarletteResponse:
        return await call_next(request)
