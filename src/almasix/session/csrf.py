"""CSRF verification for stateful ``web`` routes."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from starlette.responses import Response as StarletteResponse

from almasix.http.exceptions import HttpException
from almasix.http.middleware import Middleware, NextCall

if TYPE_CHECKING:
    from almasix.http.request import Request

_SESSION_KEY = "_csrf_token"
_SAFE = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


class TokenMismatchError(HttpException):
    """419 — CSRF token mismatch (Laravel parity)."""

    def __init__(self, message: str = "CSRF token mismatch.") -> None:
        super().__init__(message, status_code=419)


class VerifyCsrfToken(Middleware):
    """Ensure mutating requests carry a matching session CSRF token."""

    async def handle(self, request: Request, call_next: NextCall) -> StarletteResponse:
        session = request.session
        token = session.get(_SESSION_KEY)
        if not token:
            token = secrets.token_urlsafe(40)
            session.put(_SESSION_KEY, token)

        # Share with Prism ``@csrf`` / view composers.
        request._csrf_token = token

        if request.method.upper() not in _SAFE and not self._tokens_match(request, token):
            raise TokenMismatchError()

        return await call_next(request)

    def _tokens_match(self, request: Request, expected: str) -> bool:
        provided = (
            request.input("_token")
            or request.header("X-CSRF-TOKEN")
            or request.header("X-XSRF-TOKEN")
        )
        if not provided or not isinstance(provided, str):
            return False
        return secrets.compare_digest(provided, expected)


def csrf_token() -> str:
    """Return the current request CSRF token (empty when no session)."""
    from almasix.session.store import get_session

    session = get_session()
    if session is None:
        return ""
    token = session.get(_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(40)
        session.put(_SESSION_KEY, token)
    return str(token)
