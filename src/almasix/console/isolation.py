"""Isolation locks for ``--isolated`` commands (cache lock, mutex fallback)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class IsolationLock:
    """Holds whichever lock backend succeeded, so callers stay simple."""

    def __init__(self, cache_lock: Any | None = None, mutex: Any | None = None) -> None:
        self._cache_lock = cache_lock
        self._mutex = mutex

    def release(self) -> None:
        if self._cache_lock is not None:
            self._cache_lock.release()
        if self._mutex is not None:
            self._mutex.release()


def acquire(name: str, seconds: int, base_path: Path) -> IsolationLock | None:
    """Acquire the isolation lock, or return ``None`` if it is already held."""
    cache_lock = _cache_lock(name, seconds)
    if cache_lock is not None:
        return IsolationLock(cache_lock=cache_lock) if cache_lock.get() else None

    from almasix.console.mutex import Mutex

    mutex = Mutex(base_path, name)
    return IsolationLock(mutex=mutex) if mutex.acquire() else None


def _cache_lock(name: str, seconds: int) -> Any | None:
    try:
        from almasix.cache.manager import Cache

        Cache.manager()
        return Cache.lock(f"console:{name}", seconds=seconds)
    except Exception:
        return None
