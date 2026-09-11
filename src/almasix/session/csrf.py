"""CSRF verification for stateful ``web`` routes."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING
from urllib.parse import unquote

from starlette.responses import Response as StarletteResponse

from almasix.http.exceptions import HttpException
from almasix.http.middleware import Middleware, NextCall

if TYPE_CHECKING:
    from almasix.http.request import Request

_SESSION_KEY = "_csrf_token"
_XSRF_COOKIE = "XSRF-TOKEN"
_SAFE = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


class TokenMismatchError(HttpException):
    """419 — CSRF token mismatch (Laravel parity)."""

    def __init__(self, message: str = "CSRF token mismatch.") -> None:
        super().__init__(message, status_code=419)


class VerifyCsrfToken(Middleware):
    """Ensure mutating requests carry a matching session CSRF token.

    Also mints the readable ``XSRF-TOKEN`` cookie so SPA / Inertia clients can
    send it back as ``X-XSRF-TOKEN`` (Laravel parity). EncryptCookies wraps that
    cookie on the way out; this middleware decrypts the header on the way in.
    """

    async def handle(self, request: Request, call_next: NextCall) -> StarletteResponse:
        session = request.session
        token = session.get(_SESSION_KEY)
        if not token:
            token = secrets.token_urlsafe(40)
            session.put(_SESSION_KEY, token)

        # Share with Prism ``@csrf`` / view composers.
        request._csrf_token = token

        if request.method.upper() not in _SAFE and not self._tokens_match(request, str(token)):
            raise TokenMismatchError()

        response = await call_next(request)
        self._add_xsrf_cookie(response, str(token))
        return response

    def _tokens_match(self, request: Request, expected: str) -> bool:
        provided = (
            request.input("_token")
            or request.header("X-CSRF-TOKEN")
            or self._token_from_xsrf_header(request)
        )
        if not provided or not isinstance(provided, str):
            return False
        return secrets.compare_digest(provided, expected)

    def _token_from_xsrf_header(self, request: Request) -> str | None:
        header = request.header("X-XSRF-TOKEN")
        if not header or not isinstance(header, str):
            return None
        raw = unquote(header)
        decrypted = self._decrypt_xsrf(raw)
        return decrypted if decrypted is not None else raw

    def _decrypt_xsrf(self, value: str) -> str | None:
        """Decrypt an encrypted ``XSRF-TOKEN`` cookie value sent as a header."""
        if "." not in value:
            return None
        try:
            from almasix.config import config
            from almasix.encryption.encrypter import Encrypter, parse_previous_keys
            from almasix.encryption.exceptions import DecryptException

            key = str(config("app.key", "") or "") or "almasix-insecure-dev-key-change-me"
            previous = parse_previous_keys(config("app.previous_keys", []))
            return Encrypter(key, previous).decrypt_string(value)
        except DecryptException:
            return None
        except Exception:
            return None

    def _add_xsrf_cookie(self, response: StarletteResponse, token: str) -> None:
        """Expose the token to JS (``document.cookie``) for axios / Inertia."""
        from almasix.config import config

        lifetime = int(config("session.lifetime", 120) or 120) * 60
        path = str(config("session.path", "/") or "/")
        secure = bool(config("session.secure", False))
        response.set_cookie(
            _XSRF_COOKIE,
            token,
            max_age=lifetime,
            path=path,
            secure=secure,
            httponly=False,
            samesite="lax",
        )


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
