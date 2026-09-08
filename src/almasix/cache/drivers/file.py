"""File-based cache store under ``storage/framework/cache/data``."""

from __future__ import annotations

import hashlib
import pickle
import time
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - non-Unix
    fcntl = None  # type: ignore[assignment]


class FileStore:
    """Serialize values to disk (pickle) with optional expiry.

    ``add`` uses an exclusive file lock (``fcntl.flock``) so concurrent
    processes cannot race — same contract as Laravel's file store.
    Tags are **not** supported (Laravel-honest).
    """

    supports_tags = False

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.directory / digest[:2] / digest

    def get(self, key: str) -> Any:
        path = self._path(key)
        if not path.is_file():
            return None
        try:
            payload = pickle.loads(path.read_bytes())
        except Exception:
            path.unlink(missing_ok=True)
            return None
        expires = payload.get("expires")
        if expires is not None and expires <= time.time():
            path.unlink(missing_ok=True)
            return None
        return payload.get("value")

    def put(self, key: str, value: Any, seconds: int | None) -> bool:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        expires = None if seconds is None else time.time() + max(0, seconds)
        path.write_bytes(pickle.dumps({"value": value, "expires": expires}, protocol=4))
        return True

    def forever(self, key: str, value: Any) -> bool:
        return self.put(key, value, None)

    def forget(self, key: str) -> bool:
        path = self._path(key)
        if path.is_file():
            path.unlink(missing_ok=True)
            return True
        return False

    def flush(self) -> bool:
        if not self.directory.exists():
            return True
        for path in self.directory.rglob("*"):
            if path.is_file():
                path.unlink(missing_ok=True)
        return True

    def add(self, key: str, value: Any, seconds: int | None = None) -> bool:
        """Atomic add via exclusive flock (or exclusive create fallback)."""
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        expires = None if seconds is None else time.time() + max(0, seconds)
        payload = pickle.dumps({"value": value, "expires": expires}, protocol=4)

        if fcntl is None:  # pragma: no cover
            if path.is_file() and self.get(key) is not None:
                return False
            path.write_bytes(payload)
            return True

        # Open/create, take exclusive lock, then decide.
        with path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.seek(0)
            raw = handle.read()
            if raw:
                try:
                    existing = pickle.loads(raw)
                    existing_expires = existing.get("expires")
                    if existing_expires is None or existing_expires > time.time():
                        return False
                except Exception:
                    pass
            handle.seek(0)
            handle.truncate()
            handle.write(payload)
            handle.flush()
            return True

    def increment(self, key: str, amount: int = 1) -> int | bool:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)

        if fcntl is None:  # pragma: no cover
            return self._increment_unlocked(key, amount)

        with path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.seek(0)
            raw = handle.read()
            expires = None
            current: Any = None
            if raw:
                try:
                    existing = pickle.loads(raw)
                    existing_expires = existing.get("expires")
                    if existing_expires is not None and existing_expires <= time.time():
                        current = None
                    else:
                        current = existing.get("value")
                        expires = existing_expires
                except Exception:
                    current = None
            if current is None:
                next_value = amount
                new_expires = None
            else:
                try:
                    next_value = int(current) + amount
                except (TypeError, ValueError):
                    return False
                new_expires = expires
            handle.seek(0)
            handle.truncate()
            handle.write(pickle.dumps({"value": next_value, "expires": new_expires}, protocol=4))
            handle.flush()
            return next_value

    def _increment_unlocked(self, key: str, amount: int) -> int | bool:  # pragma: no cover
        current = self.get(key)
        if current is None:
            self.put(key, amount, None)
            return amount
        try:
            next_value = int(current) + amount
        except (TypeError, ValueError):
            return False
        self.put(key, next_value, None)
        return next_value

    def decrement(self, key: str, amount: int = 1) -> int | bool:
        return self.increment(key, -amount)

    def lock(self, name: str, seconds: int | None = None, owner: str | None = None) -> Any:
        from almasix.cache.locks import FileLock

        return FileLock(self, name, seconds=seconds, owner=owner)

    def flush_locks(self) -> bool:
        import shutil

        locks_dir = self.directory / ".locks"
        if locks_dir.exists():
            shutil.rmtree(locks_dir)
        return True

    def restore_lock(self, name: str, owner: str) -> Any:
        return self.lock(name, seconds=None, owner=owner)

    def _lock_path(self, name: str) -> Path:
        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
        return self.directory / ".locks" / digest
