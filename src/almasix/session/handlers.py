"""Session persistence handlers (cookie bag vs Redis-backed)."""

from __future__ import annotations

import secrets
from typing import Any, Protocol

from almasix.session.signing import sign_payload, unsign_payload


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

    def __init__(self, *, connection: str | None = None, key_prefix: str = "almasix_session:") -> None:
        self.connection = connection
        self.key_prefix = key_prefix

    def _redis(self) -> Any:
        from almasix.redis.helpers import get_manager

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


class DatabaseSessionHandler:
    """Cookie holds a signed session id; payload lives in the ``sessions`` table.

    The row carries what Laravel's does — ``user_id``, ``ip_address``,
    ``user_agent``, ``last_activity`` — because those columns are the reason to
    choose this driver over the cookie: a session you can look at, attribute to
    a user, and delete server-side.
    """

    def __init__(self, *, table: str = "sessions", connection: str | None = None) -> None:
        self.table = table
        self.connection = connection
        # A handler is built per request, and `write` receives only the
        # response — which knows nothing of the caller's address.
        self._request: Any = None

    def _query(self) -> Any:
        from almasix.orm.facade import DB

        return DB.table(self.table, connection=self.connection)

    async def read(
        self,
        request: Any,
        *,
        key: str,
        cookie_name: str,
        lifetime: int,
    ) -> tuple[str | None, dict[str, Any] | None]:
        import json

        self._request = request
        raw = request.cookie(cookie_name)
        meta = unsign_payload(raw, key=key, max_age=lifetime) if raw else None
        if not meta or not isinstance(meta, dict):
            return None, None
        session_id = str(meta.get("id") or "")
        if not session_id:
            return None, None

        row = await self._query().where("id", session_id).first()
        if not row:
            return session_id, None
        if _expired(row.get("last_activity"), lifetime):
            # An expired row is deleted rather than ignored, or the table only
            # ever grows.
            await self._query().where("id", session_id).delete()
            return session_id, None
        try:
            data = json.loads(str(row.get("payload") or "{}"))
        except ValueError:
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
        import time

        if not dirty and not had_prior and not data:
            return session_id

        sid = session_id or secrets.token_urlsafe(32)
        row = {
            "id": sid,
            "user_id": _user_id(data),
            "ip_address": _request_ip(self._request),
            "user_agent": _request_agent(self._request),
            "payload": json.dumps(data, separators=(",", ":"), default=str),
            "last_activity": int(time.time()),
        }
        await self._query().upsert([row], ["id"])
        response.set_cookie(
            cookie_name,
            sign_payload({"id": sid}, key=key, max_age=lifetime),
            max_age=lifetime,
            httponly=True,
            samesite="lax",
            path=path,
            secure=secure,
        )
        return sid

    async def destroy(self, session_id: str | None) -> None:
        if session_id:
            await self._query().where("id", session_id).delete()


def _expired(last_activity: Any, lifetime: int) -> bool:
    import time

    try:
        seen = int(last_activity)
    except (TypeError, ValueError):
        return False
    return (int(time.time()) - seen) > max(1, int(lifetime))


def _user_id(data: dict[str, Any]) -> Any:
    """The logged-in user's key, from whichever guard put it in the session."""
    for name, value in data.items():
        if name.startswith("login_") and isinstance(value, dict):
            return value.get("id")
    return None


def _request_ip(request: Any) -> str | None:
    if request is None:
        return None
    ip = getattr(request, "ip", None)
    host = ip() if callable(ip) else getattr(getattr(request, "client", None), "host", None)
    return str(host) if host else None


def _request_agent(request: Any) -> str | None:
    if request is None:
        return None
    reader = getattr(request, "user_agent", None)
    agent = reader() if callable(reader) else None
    return str(agent) if agent else None


def resolve_session_handler() -> SessionHandler:
    """Build the configured session handler."""
    from almasix.config import config

    driver = str(config("session.driver", "cookie") or "cookie").lower()
    if driver in {"cookie", "file"}:
        return CookieSessionHandler()
    if driver == "database":
        table = str(config("session.table", "sessions") or "sessions")
        connection = config("session.connection")
        return DatabaseSessionHandler(
            table=table,
            connection=str(connection) if connection else None,
        )
    if driver == "redis":
        connection = config("session.connection")
        prefix = str(config("session.prefix", "almasix_session:") or "almasix_session:")
        return RedisSessionHandler(
            connection=str(connection) if connection else None,
            key_prefix=prefix,
        )
    raise ValueError(f"Unsupported session driver: {driver!r}")
