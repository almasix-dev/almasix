"""Password hashing (Laravel ``Hash`` facade parity)."""

from __future__ import annotations

from typing import Any

from avalon.hashing.hasher import BcryptHasher, Hasher


class HashManager:
    """Resolves named hashers (default ``bcrypt``; optional ``argon2`` / ``argon2id``)."""

    def __init__(self) -> None:
        self._driver = "bcrypt"
        self._rounds = 12
        self._argon_memory = 65536
        self._argon_threads = 1
        self._argon_time = 4
        self._hashers: dict[str, Hasher] = {}

    def configure(
        self,
        *,
        driver: str | None = None,
        rounds: int | None = None,
        argon_memory: int | None = None,
        argon_threads: int | None = None,
        argon_time: int | None = None,
    ) -> None:
        if driver is not None:
            self._driver = driver
        if rounds is not None:
            self._rounds = int(rounds)
        if argon_memory is not None:
            self._argon_memory = int(argon_memory)
        if argon_threads is not None:
            self._argon_threads = int(argon_threads)
        if argon_time is not None:
            self._argon_time = int(argon_time)
        self._hashers.clear()

    def driver(self, name: str | None = None) -> Hasher:
        key = name or self._driver
        if key not in self._hashers:
            self._hashers[key] = self._create_driver(key)
        return self._hashers[key]

    def _create_driver(self, key: str) -> Hasher:
        if key == "bcrypt":
            return BcryptHasher(rounds=self._rounds)
        if key in {"argon2", "argon2id", "argon"}:
            from avalon.hashing.argon import Argon2IdHasher

            return Argon2IdHasher(
                memory=self._argon_memory,
                threads=self._argon_threads,
                time_cost=self._argon_time,
            )
        raise RuntimeError(f"Unsupported hash driver [{key}].")

    def make(self, value: str, options: dict[str, Any] | None = None) -> str:
        return self.driver().make(value, options)

    def check(self, value: str, hashed: str, options: dict[str, Any] | None = None) -> bool:
        return self.driver().check(value, hashed, options)

    def needs_rehash(self, hashed: str, options: dict[str, Any] | None = None) -> bool:
        return self.driver().needs_rehash(hashed, options)

    def is_hashed(self, value: str) -> bool:
        if self.driver().is_hashed(value):
            return True
        # Detect alternate algorithms so ``is_hashed`` stays useful regardless of default driver.
        if value.startswith("$2a$") or value.startswith("$2b$") or value.startswith("$2y$"):
            return True
        if value.startswith("$argon2"):
            return True
        return False


_manager: HashManager | None = None


def get_hash_manager() -> HashManager:
    global _manager
    if _manager is None:
        _manager = HashManager()
        try:
            from avalon.config import config

            _manager.configure(
                driver=str(config("hashing.driver", "bcrypt") or "bcrypt"),
                rounds=int(config("hashing.bcrypt.rounds", 12) or 12),
                argon_memory=int(config("hashing.argon2.memory", 65536) or 65536),
                argon_threads=int(config("hashing.argon2.threads", 1) or 1),
                argon_time=int(config("hashing.argon2.time", 4) or 4),
            )
        except Exception:
            pass
    return _manager


def set_hash_manager(manager: HashManager | None) -> None:
    global _manager
    _manager = manager


class Hash:
    """Static Laravel-shaped hashing API."""

    @staticmethod
    def make(value: str, options: dict[str, Any] | None = None) -> str:
        return get_hash_manager().make(value, options)

    @staticmethod
    def check(value: str, hashed: str, options: dict[str, Any] | None = None) -> bool:
        return get_hash_manager().check(value, hashed, options)

    @staticmethod
    def needs_rehash(hashed: str, options: dict[str, Any] | None = None) -> bool:
        return get_hash_manager().needs_rehash(hashed, options)

    @staticmethod
    def is_hashed(value: str) -> bool:
        return get_hash_manager().is_hashed(value)

    @staticmethod
    def driver(name: str | None = None) -> Hasher:
        return get_hash_manager().driver(name)


def bcrypt(value: str, options: dict[str, Any] | None = None) -> str:
    """Hash a value with bcrypt whatever the default driver is (Laravel ``bcrypt``)."""
    return get_hash_manager().driver("bcrypt").make(value, options)


__all__ = ["Hash", "HashManager", "bcrypt", "get_hash_manager", "set_hash_manager"]
