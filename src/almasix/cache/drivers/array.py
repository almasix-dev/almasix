"""In-memory array cache store (tests / default). Supports tags."""

from __future__ import annotations

import threading
import time
from typing import Any


class ArrayStore:
    """Process-local cache — values live until process exit or flush.

    ``add`` / ``increment`` are atomic within the process (threading lock).
    Tags are supported (Laravel array store); file/database raise instead.
    """

    supports_tags = True

    def __init__(self) -> None:
        self._data: dict[str, tuple[Any, float | None]] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Any:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            value, expires = item
            if expires is not None and expires <= time.time():
                self._data.pop(key, None)
                return None
            return value

    def put(self, key: str, value: Any, seconds: int | None) -> bool:
        with self._lock:
            expires = None if seconds is None else time.time() + max(0, seconds)
            self._data[key] = (value, expires)
            return True

    def forever(self, key: str, value: Any) -> bool:
        return self.put(key, value, None)

    def forget(self, key: str) -> bool:
        with self._lock:
            return self._data.pop(key, None) is not None

    def flush(self) -> bool:
        with self._lock:
            self._data.clear()
            return True

    def add(self, key: str, value: Any, seconds: int | None) -> bool:
        """Atomic within-process add (check-then-set under lock)."""
        with self._lock:
            item = self._data.get(key)
            if item is not None:
                _value, expires = item
                if expires is None or expires > time.time():
                    return False
                self._data.pop(key, None)
            expires = None if seconds is None else time.time() + max(0, seconds)
            self._data[key] = (value, expires)
            return True

    def increment(self, key: str, amount: int = 1) -> int | bool:
        with self._lock:
            item = self._data.get(key)
            if item is not None:
                current, expires = item
                if expires is not None and expires <= time.time():
                    self._data.pop(key, None)
                    item = None
            if item is None:
                self._data[key] = (amount, None)
                return amount
            current, expires = item
            try:
                next_value = int(current) + amount
            except (TypeError, ValueError):
                return False
            ttl = None if expires is None else max(0, int(expires - time.time()))
            new_expires = None if ttl is None else time.time() + ttl
            self._data[key] = (next_value, new_expires)
            return next_value

    def decrement(self, key: str, amount: int = 1) -> int | bool:
        return self.increment(key, -amount)

    def flush_locks(self) -> bool:
        with self._lock:
            for key in [k for k in self._data if "lock:" in k]:
                self._data.pop(key, None)
            return True
