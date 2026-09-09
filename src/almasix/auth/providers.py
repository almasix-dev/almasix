"""User providers — Articulate (Eloquent-shaped) and in-memory."""

from __future__ import annotations

from typing import Any

from almasix.hashing import Hash


class ArticulateUserProvider:
    """Retrieve users via an Articulate ``Model`` class."""

    def __init__(self, model: type) -> None:
        self.model = model

    async def retrieve_by_id(self, identifier: Any) -> Any | None:
        return await self.model.query().find(identifier)

    async def retrieve_by_token(self, identifier: Any, token: str) -> Any | None:
        user = await self.retrieve_by_id(identifier)
        if user is None:
            return None
        remember = _remember_token(user)
        if remember and remember == token:
            return user
        return None

    async def update_remember_token(self, user: Any, token: str | None) -> None:
        if hasattr(user, "set_remember_token"):
            user.set_remember_token(token)
        else:
            user.remember_token = token
        if hasattr(user, "save"):
            await user.save()

    async def retrieve_by_credentials(self, credentials: dict[str, Any]) -> Any | None:
        query = self.model.query()
        applied = False
        for key, value in credentials.items():
            if key in {"password", "password_confirmation"}:
                continue
            query = query.where(key, value)
            applied = True
        if not applied:
            return None
        return await query.first()

    async def validate_credentials(self, user: Any, credentials: dict[str, Any]) -> bool:
        plain = credentials.get("password")
        if plain is None:
            return False
        hashed = _password(user)
        if not hashed:
            return False
        return Hash.check(str(plain), str(hashed))

    async def rehash_password_if_required(
        self,
        user: Any,
        credentials: dict[str, Any],
        *,
        force: bool = False,
    ) -> None:
        plain = credentials.get("password")
        hashed = _password(user)
        if plain is None or not hashed:
            return
        if force or Hash.needs_rehash(str(hashed)):
            new_hash = Hash.make(str(plain))
            if hasattr(user, "set_attribute"):
                user.set_attribute("password", new_hash)
            else:
                user.password = new_hash
            if hasattr(user, "save"):
                await user.save()


class MemoryUserProvider:
    """Dict-backed provider for tests and demos without a database."""

    def __init__(self, users: list[dict[str, Any]] | None = None) -> None:
        self.users = list(users or [])

    async def retrieve_by_id(self, identifier: Any) -> dict[str, Any] | None:
        for user in self.users:
            if user.get("id") == identifier or str(user.get("id")) == str(identifier):
                return user
        return None

    async def retrieve_by_token(self, identifier: Any, token: str) -> dict[str, Any] | None:
        user = await self.retrieve_by_id(identifier)
        if user and user.get("remember_token") == token:
            return user
        return None

    async def update_remember_token(self, user: dict[str, Any], token: str | None) -> None:
        user["remember_token"] = token

    async def retrieve_by_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        for user in self.users:
            match = True
            for key, value in credentials.items():
                if key in {"password", "password_confirmation"}:
                    continue
                if user.get(key) != value:
                    match = False
                    break
            if match:
                return user
        return None

    async def validate_credentials(self, user: dict[str, Any], credentials: dict[str, Any]) -> bool:
        plain = credentials.get("password")
        hashed = user.get("password")
        if plain is None or not hashed:
            return False
        return Hash.check(str(plain), str(hashed))

    async def rehash_password_if_required(
        self,
        user: dict[str, Any],
        credentials: dict[str, Any],
        *,
        force: bool = False,
    ) -> None:
        plain = credentials.get("password")
        hashed = user.get("password")
        if plain is None or not hashed:
            return
        if force or Hash.needs_rehash(str(hashed)):
            user["password"] = Hash.make(str(plain))
            for idx, row in enumerate(self.users):
                if row.get("id") == user.get("id"):
                    self.users[idx] = dict(user)
                    break


def _password(user: Any) -> str | None:
    if hasattr(user, "get_auth_password"):
        return user.get_auth_password()
    if isinstance(user, dict):
        value = user.get("password")
        return str(value) if value is not None else None
    if hasattr(user, "get_attribute"):
        value = user.get_attribute("password")
        return str(value) if value is not None else None
    value = getattr(user, "password", None)
    return str(value) if value is not None else None


def _remember_token(user: Any) -> str | None:
    if hasattr(user, "get_remember_token"):
        return user.get_remember_token()
    if isinstance(user, dict):
        value = user.get("remember_token")
        return str(value) if value is not None else None
    value = getattr(user, "remember_token", None)
    return str(value) if value is not None else None
