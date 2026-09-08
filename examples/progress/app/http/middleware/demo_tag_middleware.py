"""Demo middleware — proves alias resolution + pipeline for M2."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from almasix.http import Middleware, Request


class DemoTagMiddleware(Middleware):
    async def handle(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Any]],
    ) -> Any:
        response = await call_next(request)
        response.headers["X-Almasix-Demo"] = "m2"
        response.headers["X-Almasix-Path"] = request.path
        return response
