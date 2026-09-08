"""Hasher drivers."""

from __future__ import annotations

from typing import Any, Protocol

import bcrypt


class Hasher(Protocol):
    def make(self, value: str, options: dict[str, Any] | None = None) -> str:  # pragma: no cover
        ...

    def check(  # pragma: no cover
        self, value: str, hashed: str, options: dict[str, Any] | None = None
    ) -> bool:
        ...

    def needs_rehash(  # pragma: no cover
        self, hashed: str, options: dict[str, Any] | None = None
    ) -> bool:
        ...

    def is_hashed(self, value: str) -> bool:  # pragma: no cover
        ...


class BcryptHasher:
    """Bcrypt password hasher (Laravel default)."""

    def __init__(self, rounds: int = 12) -> None:
        self.rounds = rounds

    def make(self, value: str, options: dict[str, Any] | None = None) -> str:
        rounds = int((options or {}).get("rounds", self.rounds))
        salt = bcrypt.gensalt(rounds=rounds)
        return bcrypt.hashpw(value.encode("utf-8"), salt).decode("ascii")

    def check(self, value: str, hashed: str, options: dict[str, Any] | None = None) -> bool:
        if not hashed:
            return False
        if not self.is_hashed(hashed):
            raise RuntimeError("This password does not use the Bcrypt algorithm.")
        try:
            return bcrypt.checkpw(value.encode("utf-8"), hashed.encode("ascii"))
        except (ValueError, TypeError):
            return False

    def needs_rehash(self, hashed: str, options: dict[str, Any] | None = None) -> bool:
        if not self.is_hashed(hashed):
            return True
        rounds = int((options or {}).get("rounds", self.rounds))
        try:
            # bcrypt hashes encode cost as $2b$12$...
            parts = hashed.split("$")
            cost = int(parts[2]) if len(parts) > 2 else -1
        except (IndexError, ValueError):
            return True
        return cost != rounds

    def is_hashed(self, value: str) -> bool:
        return bool(value) and (
            value.startswith("$2a$") or value.startswith("$2b$") or value.startswith("$2y$")
        )
