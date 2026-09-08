"""Argon2id password hasher (optional ``argon2-cffi``)."""

from __future__ import annotations

from typing import Any


class Argon2IdHasher:
    """Laravel ``argon2id`` driver — requires the ``argon2-cffi`` package."""

    def __init__(
        self,
        *,
        memory: int = 65536,
        threads: int = 1,
        time_cost: int = 4,
    ) -> None:
        self.memory = memory
        self.threads = threads
        self.time_cost = time_cost
        self._password_hasher = self._build()

    def _build(self) -> Any:
        try:
            from argon2 import PasswordHasher
            from argon2.low_level import Type
        except ImportError as exc:  # pragma: no cover - exercised via HashManager
            raise RuntimeError(
                "Hash driver [argon2] requires the argon2-cffi package. "
                "Install with: pip install 'almasix[argon2]' or pip install argon2-cffi"
            ) from exc
        return PasswordHasher(
            memory_cost=self.memory,
            time_cost=self.time_cost,
            parallelism=self.threads,
            type=Type.ID,
        )

    def make(self, value: str, options: dict[str, Any] | None = None) -> str:
        hasher = self._hasher_from_options(options)
        return hasher.hash(value)

    def check(self, value: str, hashed: str, options: dict[str, Any] | None = None) -> bool:
        if not hashed:
            return False
        if not self.is_hashed(hashed):
            raise RuntimeError("This password does not use the Argon2 algorithm.")
        try:
            from argon2.exceptions import VerifyMismatchError

            self._password_hasher.verify(hashed, value)
            return True
        except VerifyMismatchError:
            return False
        except Exception:
            return False

    def needs_rehash(self, hashed: str, options: dict[str, Any] | None = None) -> bool:
        if not self.is_hashed(hashed):
            return True
        hasher = self._hasher_from_options(options)
        try:
            return bool(hasher.check_needs_rehash(hashed))
        except Exception:
            return True

    def is_hashed(self, value: str) -> bool:
        return bool(value) and value.startswith("$argon2")

    def _hasher_from_options(self, options: dict[str, Any] | None) -> Any:
        if not options:
            return self._password_hasher
        memory = int(options.get("memory", self.memory))
        threads = int(options.get("threads", self.threads))
        time_cost = int(options.get("time", options.get("time_cost", self.time_cost)))
        if memory == self.memory and threads == self.threads and time_cost == self.time_cost:
            return self._password_hasher
        clone = Argon2IdHasher(memory=memory, threads=threads, time_cost=time_cost)
        return clone._password_hasher
