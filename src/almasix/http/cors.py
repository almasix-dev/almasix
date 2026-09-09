"""CORS — which origins may call this application from a browser.

Browsers refuse a `fetch` from `https://app.test` to `https://api.test` unless
the API answers with the right `Access-Control-*` headers. Laravel's
`config/cors.php` is the shape of this configuration; Starlette's
`CORSMiddleware` is what actually writes the headers. This module is the
bridge: it reads the config, matches the request path against `paths`, and
mounts Starlette's middleware only for those paths.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from starlette.middleware.cors import CORSMiddleware as StarletteCORS
from starlette.types import ASGIApp, Receive, Scope, Send

#: Defaults mirror Laravel's `config/cors.php` so an application that never
#: opens the file still gets a working API that any origin may call.
DEFAULTS: dict[str, Any] = {
    "paths": ["api/*", "sanctum/csrf-cookie"],
    "allowed_methods": ["*"],
    "allowed_origins": ["*"],
    "allowed_origins_patterns": [],
    "allowed_headers": ["*"],
    "exposed_headers": [],
    "max_age": 0,
    "supports_credentials": False,
}


def cors_settings(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Merge ``config`` onto the defaults, the way Laravel loads the file."""
    return {**DEFAULTS, **dict(config or {})}


class HandleCors:
    """ASGI middleware: CORS for paths that match `config/cors.py`.

    Starlette's middleware applies to every path. Laravel's only answers for
    paths listed under `paths`, so a marketing page at `/` does not sprout
    `Access-Control-Allow-Origin: *`. Matching is done here; the headers are
    Starlette's.
    """

    def __init__(self, app: ASGIApp, settings: Mapping[str, Any] | None = None) -> None:
        self.app = app
        self.settings = cors_settings(settings)
        self.paths = [str(path) for path in self.settings.get("paths") or []]
        origins = list(self.settings.get("allowed_origins") or [])
        patterns = list(self.settings.get("allowed_origins_patterns") or [])
        # Starlette takes one regex for origins; Laravel takes a list. Join
        # them the way a browser would match either.
        origin_regex = "|".join(f"(?:{pattern})" for pattern in patterns) or None
        allow_origins = [] if origin_regex and origins == ["*"] else origins
        self._cors = StarletteCORS(
            app,
            allow_origins=allow_origins,
            allow_origin_regex=origin_regex,
            allow_methods=_star(self.settings.get("allowed_methods")),
            allow_headers=_star(self.settings.get("allowed_headers")),
            allow_credentials=bool(self.settings.get("supports_credentials")),
            expose_headers=list(self.settings.get("exposed_headers") or []),
            max_age=int(self.settings.get("max_age") or 0),
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or not self._matches(scope.get("path", "")):
            await self.app(scope, receive, send)
            return
        await self._cors(scope, receive, send)

    def _matches(self, path: str) -> bool:
        path = path or "/"
        return any(_path_matches(pattern, path) for pattern in self.paths)


def _star(values: Sequence[str] | None) -> list[str]:
    items = [str(value) for value in (values or [])]
    return ["*"] if items == ["*"] else items


def _path_matches(pattern: str, path: str) -> bool:
    """Laravel's `api/*` style match — `*` is one or more path segments."""
    pattern = "/" + pattern.strip("/")
    path = "/" + path.strip("/") if path != "/" else "/"
    if pattern.endswith("/*"):
        prefix = pattern[:-1]  # keep the trailing slash of the prefix
        return path == pattern[:-2] or path.startswith(prefix)
    if pattern.endswith("*"):
        return path.startswith(pattern[:-1])
    return path == pattern
