"""Password reset broker (Laravel ``Password`` facade core)."""

from __future__ import annotations

import hashlib
import secrets
import time
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from almasix.auth import events as auth_events
from almasix.translation import __

RESET_LINK_SENT = "passwords.sent"
PASSWORD_RESET = "passwords.reset"
INVALID_USER = "passwords.user"
INVALID_TOKEN = "passwords.token"
RESET_THROTTLED = "passwords.throttled"

SendCallback = Callable[[Any, str], Awaitable[None] | None]


class TokenRepository(Protocol):
    async def create(self, email: str) -> str:  # pragma: no cover
        ...

    async def exists(self, email: str, token: str) -> bool:  # pragma: no cover
        ...

    async def recently_created(self, email: str) -> bool:  # pragma: no cover
        ...

    async def delete(self, email: str) -> None:  # pragma: no cover
        ...

    async def delete_expired(self) -> int:  # pragma: no cover
        ...


class DatabaseTokenRepository:
    """In-memory token repository (default). Implements the Laravel table shape.

    When ``use_database=True`` and a connection is available, rows are stored in
    ``password_reset_tokens`` (email / token / created_at).
    """

    def __init__(
        self,
        *,
        expire: int = 60,
        throttle: int = 60,
        table: str = "password_reset_tokens",
        use_database: bool = False,
    ) -> None:
        self.expire = expire * 60
        self.throttle = throttle
        self.table = table
        self.use_database = use_database
        self._tokens: dict[str, dict[str, Any]] = {}

    async def create(self, email: str) -> str:
        token = secrets.token_urlsafe(32)
        row = {
            "email": email.lower(),
            "token": _hash_token(token),
            "created_at": time.time(),
        }
        await self.delete(email)
        if self.use_database and await self._db_insert(row):
            return token
        self._tokens[email.lower()] = row
        return token

    async def exists(self, email: str, token: str) -> bool:
        row = await self._get(email)
        if row is None:
            return False
        if (time.time() - float(row["created_at"])) > self.expire:
            return False
        return secrets.compare_digest(str(row["token"]), _hash_token(token))

    async def recently_created(self, email: str) -> bool:
        row = await self._get(email)
        if row is None:
            return False
        return (time.time() - float(row["created_at"])) < self.throttle

    async def delete(self, email: str) -> None:
        self._tokens.pop(email.lower(), None)
        if self.use_database:
            await self._db_delete(email)

    async def delete_expired(self) -> int:
        now = time.time()
        stale = [k for k, v in self._tokens.items() if (now - float(v["created_at"])) > self.expire]
        for key in stale:
            del self._tokens[key]
        removed = len(stale)
        if self.use_database:
            removed += await self._db_delete_expired(now)
        return removed

    async def _get(self, email: str) -> dict[str, Any] | None:
        key = email.lower()
        if key in self._tokens:
            return self._tokens[key]
        if self.use_database:
            return await self._db_get(key)
        return None

    async def _db_insert(self, row: dict[str, Any]) -> bool:
        try:
            from almasix.orm.facade import DB

            await DB.statement(
                f"INSERT INTO {self.table} (email, token, created_at) "
                "VALUES (:email, :token, :created_at)",
                {
                    "email": row["email"],
                    "token": row["token"],
                    "created_at": row["created_at"],
                },
            )
            return True
        except Exception:
            return False

    async def _db_get(self, email: str) -> dict[str, Any] | None:
        try:
            from almasix.orm.facade import DB

            rows = await DB.select(
                f"SELECT email, token, created_at FROM {self.table} WHERE email = :email",
                {"email": email},
            )
            if not rows:
                return None
            result = rows[0]
            created = result["created_at"]
            if hasattr(created, "timestamp"):
                created = created.timestamp()
            return {
                "email": result["email"],
                "token": result["token"],
                "created_at": float(created),
            }
        except Exception:
            return None

    async def _db_delete(self, email: str) -> None:
        try:
            from almasix.orm.facade import DB

            await DB.statement(
                f"DELETE FROM {self.table} WHERE email = :email",
                {"email": email.lower()},
            )
        except Exception:
            return

    async def _db_delete_expired(self, now: float) -> int:
        try:
            from almasix.orm.facade import DB

            cutoff = now - self.expire
            await DB.statement(
                f"DELETE FROM {self.table} WHERE created_at < :cutoff",
                {"cutoff": cutoff},
            )
            return 0
        except Exception:
            return 0


class PasswordBroker:
    """Create and consume password reset tokens."""

    def __init__(
        self,
        provider: Any,
        tokens: TokenRepository,
        *,
        send_callback: SendCallback | None = None,
    ) -> None:
        self.provider = provider
        self.tokens = tokens
        self.send_callback = send_callback

    async def send_reset_link(self, credentials: dict[str, Any]) -> str:
        if self.provider is None:
            return INVALID_USER
        email = str(credentials.get("email") or "")
        user = await self.provider.retrieve_by_credentials({"email": email})
        if user is None:
            return INVALID_USER
        if await self.tokens.recently_created(email):
            return RESET_THROTTLED
        token = await self.tokens.create(email)
        if self.send_callback is not None:
            result = self.send_callback(user, token)
            if hasattr(result, "__await__"):
                await result  # type: ignore[misc]
        return RESET_LINK_SENT

    async def reset(
        self,
        credentials: dict[str, Any],
        callback: Callable[[Any, str], Awaitable[None] | None],
    ) -> str:
        if self.provider is None:
            return INVALID_USER
        email = str(credentials.get("email") or "")
        token = str(credentials.get("token") or "")
        password = str(credentials.get("password") or "")
        user = await self.provider.retrieve_by_credentials({"email": email})
        if user is None:
            return INVALID_USER
        if not await self.tokens.exists(email, token):
            return INVALID_TOKEN
        result = callback(user, password)
        if hasattr(result, "__await__"):
            await result  # type: ignore[misc]
        await self.tokens.delete(email)
        await auth_events.dispatch(auth_events.PasswordReset(user=user))
        return PASSWORD_RESET


class PasswordBrokerManager:
    def __init__(self) -> None:
        self._brokers: dict[str, PasswordBroker] = {}
        self._send_callback: SendCallback | None = None

    def create_url_using(self, callback: SendCallback) -> None:
        """Register the delivery callback (mail/notifications later)."""
        self._send_callback = callback

    def broker(self, name: str | None = None) -> PasswordBroker:
        key = name or self._default_broker()
        if key not in self._brokers:
            from almasix.auth.guard import auth

            provider_name = key
            table = "password_reset_tokens"
            expire, throttle = 60, 60
            use_database = False
            try:
                from almasix.config import config

                provider_name = str(config(f"auth.passwords.{key}.provider", key) or key)
                table = str(
                    config(f"auth.passwords.{key}.table", "password_reset_tokens")
                    or "password_reset_tokens"
                )
                expire = int(config(f"auth.passwords.{key}.expire", 60) or 60)
                throttle = int(config(f"auth.passwords.{key}.throttle", 60) or 60)
                use_database = bool(config(f"auth.passwords.{key}.use_database", False))
            except Exception:
                pass
            provider = auth()._resolve_provider(provider_name)
            tokens = DatabaseTokenRepository(
                expire=expire,
                throttle=throttle,
                table=table,
                use_database=use_database,
            )
            self._brokers[key] = PasswordBroker(
                provider,
                tokens,
                send_callback=self._send_callback,
            )
        return self._brokers[key]

    def _default_broker(self) -> str:
        try:
            from almasix.config import config

            return str(config("auth.defaults.passwords", "users") or "users")
        except Exception:
            return "users"


_password_manager: PasswordBrokerManager | None = None


def get_password_manager() -> PasswordBrokerManager:
    global _password_manager
    if _password_manager is None:
        _password_manager = PasswordBrokerManager()
    return _password_manager


def set_password_manager(manager: PasswordBrokerManager | None) -> None:
    global _password_manager
    _password_manager = manager


class Password:
    """Static Laravel-shaped password broker API."""

    RESET_LINK_SENT = RESET_LINK_SENT
    PASSWORD_RESET = PASSWORD_RESET
    INVALID_USER = INVALID_USER
    INVALID_TOKEN = INVALID_TOKEN
    RESET_THROTTLED = RESET_THROTTLED

    @staticmethod
    async def send_reset_link(credentials: dict[str, Any]) -> str:
        return await get_password_manager().broker().send_reset_link(credentials)

    @staticmethod
    async def reset(
        credentials: dict[str, Any],
        callback: Callable[[Any, str], Awaitable[None] | None],
    ) -> str:
        return await get_password_manager().broker().reset(credentials, callback)

    @staticmethod
    def broker(name: str | None = None) -> PasswordBroker:
        return get_password_manager().broker(name)

    @staticmethod
    def status_message(status: str) -> str:
        return __(status)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
