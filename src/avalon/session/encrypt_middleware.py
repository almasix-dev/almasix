"""Encrypt cookies on the way out; decrypt on the way in."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from starlette.responses import Response as StarletteResponse

from avalon.encryption.cipher import encrypt_string
from avalon.encryption.encrypter import Encrypter, parse_previous_keys
from avalon.encryption.exceptions import DecryptException
from avalon.http.middleware import Middleware, NextCall

if TYPE_CHECKING:
    from avalon.http.request import Request


class EncryptCookies(Middleware):
    """Authenticated cookie encryption using ``app.key`` (+ previous keys)."""

    except_cookies: ClassVar[frozenset[str]] = frozenset()

    async def handle(self, request: Request, call_next: NextCall) -> StarletteResponse:
        from avalon.config import config

        key = str(config("app.key", "") or "") or "avalon-insecure-dev-key-change-me"
        previous = parse_previous_keys(config("app.previous_keys", []))
        encrypter = Encrypter(key, previous)
        bag: dict[str, str] = {}
        for name, value in dict(request.raw.cookies).items():
            if name in self.except_cookies:
                bag[name] = value
                continue
            try:
                bag[name] = encrypter.decrypt_string(value)
            except DecryptException:
                bag[name] = value
        request._cookies = bag

        response = await call_next(request)
        self._encrypt_response_cookies(response, key=key)
        return response

    def _encrypt_response_cookies(self, response: StarletteResponse, *, key: str) -> None:
        # Starlette stores cookies via set_cookie; re-encrypt values on raw headers.
        headers = getattr(response, "raw_headers", None)
        if headers is None:
            return
        updated: list[tuple[bytes, bytes]] = []
        changed = False
        for name, value in headers:
            if name.lower() != b"set-cookie":
                updated.append((name, value))
                continue
            rewritten = self._encrypt_set_cookie(value.decode("latin-1"), key=key)
            if rewritten != value.decode("latin-1"):
                changed = True
            updated.append((name, rewritten.encode("latin-1")))
        if changed:  # pragma: no branch
            response.raw_headers[:] = updated

    def _encrypt_set_cookie(self, header: str, *, key: str) -> str:
        if "=" not in header:
            return header
        name, rest = header.split("=", 1)
        cookie_name = name.strip()
        if cookie_name in self.except_cookies:
            return header
        value, sep, attrs = rest.partition(";")
        # Already encrypted payloads have three dotted segments from encrypt_string,
        # but session cookies also use three segments — always wrap once.
        encrypted = encrypt_string(value, key=key)
        if sep:
            return f"{cookie_name}={encrypted};{attrs}"
        return f"{cookie_name}={encrypted}"
