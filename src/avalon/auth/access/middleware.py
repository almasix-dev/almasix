"""``can`` middleware — ``can:update,post`` / ``can:create,app.models.post.Post``."""

from __future__ import annotations

import importlib
from typing import Any

from starlette.responses import Response as StarletteResponse

from avalon.auth.access.facade import Gate
from avalon.http.middleware import Middleware, NextCall

if False:  # pragma: no cover — typing only without importing Request at runtime cycle
    pass


class Authorize(Middleware):
    """Authorize an ability, optionally against a route parameter or class."""

    def __init__(self, ability_and_models: str = "") -> None:
        parts = [part.strip() for part in str(ability_and_models).split(",") if part.strip()]
        self.ability = parts[0] if parts else ""
        self.models = parts[1:]

    async def handle(self, request: Any, call_next: NextCall) -> StarletteResponse:
        arguments = self._arguments(request)
        if not self.ability:
            return await call_next(request)
        payload: Any
        if not arguments:
            payload = None
        elif len(arguments) == 1:
            payload = arguments[0]
        else:
            payload = arguments
        Gate.authorize(self.ability, payload)
        return await call_next(request)

    def _arguments(self, request: Any) -> list[Any]:
        values: list[Any] = []
        params = getattr(request, "path_params", {}) or {}
        for token in self.models:
            if token in params:
                values.append(params[token])
                continue
            if "." in token:
                imported = _import_string(token)
                if imported is not None:
                    values.append(imported)
                    continue
            values.append(token)
        return values


def _import_string(path: str) -> Any | None:
    module_path, _, name = path.rpartition(".")
    if not module_path:
        return None
    try:
        module = importlib.import_module(module_path)
        return getattr(module, name, None)
    except Exception:
        return None
