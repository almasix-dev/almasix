"""Session persistence handlers (cookie bag vs Redis-backed)."""

from __future__ import annotations

import secrets
from typing import Any, Protocol

from avalon.session.signing import sign_payload, unsign_payload


class SessionHandler(Protocol):
    """Load / persist session bags for ``StartSession``."""

    async def read(self, request: Any, *, key: str, cookie_name: str, lifetime: int) -> tuple[str | None, dict[str, Any] | None]:
        """Return ``(session_id, data)`` — data may be ``None`` for a new session."""
        ...  # pragma: no cover

    async def write(
        self,
        response: Any,
        *,
        session_id: str | None,
        data: dict[str, Any],
        key: str,
        cookie_name: str,
        lifetime: int,
        path: str,
        secure: bool,
        dirty: bool,
        had_prior: bool,
    ) -> str | None:
        """Persist and set cookies. Return the session id used."""
        ...  # pragma: no cover

    async def destroy(self, session_id: str | None) -> None:
        ...  # pragma: no cover


class CookieSessionHandler:
    """Signed cookie holds the full session payload (default)."""

    async def read(
        self,
        request: Any,
        *,
        key: str,
        cookie_name: str,
        lifetime: int,
    ) -> tuple[str | None, dict[str, Any] | None]:
        raw = request.cookie(cookie_name)
        data = unsign_payload(raw, key=key, max_age=lifetime) if raw else None
        return None, data

    async def write(
        self,
        response: Any,
        *,
        session_id: str | None,
        data: dict[str, Any],
        key: str,
        cookie_name: str,
        lifetime: int,
        path: str,
        secure: bool,
        dirty: bool,
        had_prior: bool,
    ) -> str | None:
        del session_id
        if dirty or had_prior:
            value = sign_payload(data, key=key, max_age=lifetime)
            response.set_cookie(
                cookie_name,
                value,
                max_age=lifetime,
                httponly=True,
                samesite="lax",
                path=path,
                secure=secure,
            )
        return None

    async def destroy(self, session_id: str | None) -> None:
        del session_id


class RedisSessionHandler:
    """Cookie holds a signed session id; payload lives in Redis."""

    def __init__(self, *, connection: str | None = None, key_prefix: str = "avalon_session:") -> None:
        self.connection = connection
        self.key_prefix = key_prefix

    def _redis(self) -> Any:
        from avalon.redis.helpers import get_manager

        return get_manager().connection(self.connection)

    def _redis_key(self, session_id: str) -> str:
        return f"{self.key_prefix}{session_id}"

    async def read(
        self,
        request: Any,
        *,
        key: str,
        cookie_name: str,
        lifetime: int,
    ) -> tuple[str | None, dict[str, Any] | None]:
        import json

        raw = request.cookie(cookie_name)
        meta = unsign_payload(raw, key=key, max_age=lifetime) if raw else None
        if not meta or not isinstance(meta, dict):
            return None, None
        session_id = str(meta.get("id") or "")
        if not session_id:
            return None, None
        payload = await self._redis().get(self._redis_key(session_id))
        if payload is None:
            return session_id, None
        try:
            text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else str(payload)
            data = json.loads(text)
        except Exception:
            return session_id, None
        return session_id, data if isinstance(data, dict) else None

    async def write(
        self,
        response: Any,
        *,
        session_id: str | None,
        data: dict[str, Any],
        key: str,
        cookie_name: str,
        lifetime: int,
        path: str,
        secure: bool,
        dirty: bool,
        had_prior: bool,
    ) -> str | None:
        import json

        if not dirty and not had_prior and not data:
            return session_id

        sid = session_id or secrets.token_urlsafe(32)
        await self._redis().set(
            self._redis_key(sid),
            json.dumps(data, separators=(",", ":"), default=str).encode("utf-8"),
            ex=max(1, int(lifetime)),
        )
        cookie_value = sign_payload({"id": sid}, key=key, max_age=lifetime)
        response.set_cookie(
            cookie_name,
            cookie_value,
            max_age=lifetime,
            httponly=True,
            samesite="lax",
            path=path,
            secure=secure,
        )
        return sid

    async def destroy(self, session_id: str | None) -> None:
        if session_id:
            await self._redis().delete(self._redis_key(session_id))


def resolve_session_handler() -> SessionHandler:
    """Build the configured session handler."""
    from avalon.config import config

    driver = str(config("session.driver", "cookie") or "cookie").lower()
    if driver in {"cookie", "file"}:
        return CookieSessionHandler()
    if driver == "redis":
        connection = config("session.connection")
        prefix = str(config("session.prefix", "avalon_session:") or "avalon_session:")
        return RedisSessionHandler(
            connection=str(connection) if connection else None,
            key_prefix=prefix,
        )
    raise ValueError(f"Unsupported session driver: {driver!r}")
