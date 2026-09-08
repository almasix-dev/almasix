"""HTTP middleware base type."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from starlette.responses import Response as StarletteResponse

if TYPE_CHECKING:
    from almasix.http.request import Request

NextCall = Callable[["Request"], Awaitable[StarletteResponse]]


class Middleware:
    """Laravel-style middleware with ``handle(request, next)``."""

    async def handle(self, request: Request, call_next: NextCall) -> StarletteResponse:
        return await call_next(request)
