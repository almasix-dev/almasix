"""Cache store protocol and repository (Laravel ``Illuminate\\Cache\\Repository``)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol


def normalize_ttl(seconds: Any) -> int | None:
    """Convert TTL inputs to integer seconds (``None`` = forever)."""
    if seconds is None:
        return None
    if isinstance(seconds, timedelta):
        return max(0, int(seconds.total_seconds()))
    if isinstance(seconds, datetime):
        now = datetime.now(timezone.utc)
        target = seconds if seconds.tzinfo else seconds.replace(tzinfo=timezone.utc)
        return max(0, int((target - now).total_seconds()))
    return max(0, int(seconds))


class Store(Protocol):
    """Low-level cache driver."""

    supports_tags: bool

    def get(self, key: str) -> Any: ...  # pragma: no cover

    def put(self, key: str, value: Any, seconds: int | None) -> bool: ...  # pragma: no cover

    def forever(self, key: str, value: Any) -> bool: ...  # pragma: no cover

    def forget(self, key: str) -> bool: ...  # pragma: no cover

    def flush(self) -> bool: ...  # pragma: no cover

    def add(self, key: str, value: Any, seconds: int | None) -> bool: ...  # pragma: no cover

    def increment(self, key: str, amount: int = 1) -> int | bool: ...  # pragma: no cover

    def decrement(self, key: str, amount: int = 1) -> int | bool: ...  # pragma: no cover


class Repository:
    """High-level cache API over a store (prefix + helpers)."""

    def __init__(self, store: Store, *, prefix: str = "") -> None:
        self.store = store
        self.prefix = prefix

    def _key(self, key: str) -> str:
        return f"{self.prefix}{key}" if self.prefix else key

    def get(self, key: str, default: Any = None) -> Any:
        value = self.store.get(self._key(key))
        if value is None:
            return default() if callable(default) else default
        return value

    def many(self, keys: list[str]) -> dict[str, Any]:
        return {key: self.get(key) for key in keys}

    def put(self, key: str, value: Any, seconds: Any = None) -> bool:
        return self.store.put(self._key(key), value, normalize_ttl(seconds))

    def put_many(self, values: dict[str, Any], seconds: Any = None) -> bool:
        ok = True
        ttl = normalize_ttl(seconds)
        for key, value in values.items():
            ok = self.store.put(self._key(key), value, ttl) and ok
        return ok

    def forever(self, key: str, value: Any) -> bool:
        return self.store.forever(self._key(key), value)

    def add(self, key: str, value: Any, seconds: Any = None) -> bool:
        return self.store.add(self._key(key), value, normalize_ttl(seconds))

    def forget(self, key: str) -> bool:
        return self.store.forget(self._key(key))

    def delete(self, key: str) -> bool:
        return self.forget(key)

    def flush(self) -> bool:
        return self.store.flush()

    def has(self, key: str) -> bool:
        return self.store.get(self._key(key)) is not None

    def missing(self, key: str) -> bool:
        return not self.has(key)

    def pull(self, key: str, default: Any = None) -> Any:
        value = self.get(key, default)
        self.forget(key)
        return value

    def touch(self, key: str, seconds: Any = None) -> bool:
        """Refresh TTL without changing the value (Laravel ``Cache::touch``)."""
        value = self.store.get(self._key(key))
        if value is None:
            return False
        return self.put(key, value, seconds)

    def remember(self, key: str, seconds: Any, callback: Callable[[], Any]) -> Any:
        value = self.store.get(self._key(key))
        if value is not None:
            return value
        value = callback()
        self.put(key, value, seconds)
        return value

    def remember_forever(self, key: str, callback: Callable[[], Any]) -> Any:
        value = self.store.get(self._key(key))
        if value is not None:
            return value
        value = callback()
        self.forever(key, value)
        return value

    def sear(self, key: str, callback: Callable[[], Any]) -> Any:
        return self.remember_forever(key, callback)

    def increment(self, key: str, amount: int = 1) -> int | bool:
        return self.store.increment(self._key(key), amount)

    def decrement(self, key: str, amount: int = 1) -> int | bool:
        return self.store.decrement(self._key(key), amount)

    def lock(self, name: str, seconds: int | None = None, owner: str | None = None) -> Any:
        store_lock = getattr(self.store, "lock", None)
        if callable(store_lock):
            return store_lock(self._key(name), seconds=seconds, owner=owner)
        from almasix.cache.locks import CacheLock

        return CacheLock(self, name, seconds=seconds, owner=owner)

    def restore_lock(self, name: str, owner: str) -> Any:
        restore = getattr(self.store, "restore_lock", None)
        if callable(restore):
            return restore(self._key(name), owner)
        return self.lock(name, seconds=None, owner=owner)

    def flush_locks(self) -> bool:
        flush = getattr(self.store, "flush_locks", None)
        if callable(flush):
            return bool(flush())
        return True

    def tags(self, *names: str) -> TaggedCache:
        if not getattr(self.store, "supports_tags", False):
            raise RuntimeError(
                "Cache tags are not supported by this store. "
                "Use the array or redis store."
            )
        return TaggedCache(self, list(names))


class TaggedCache:
    """Tagged cache for taggable stores (array / redis).

    Keys are namespaced by the sorted tag set; ``flush()`` clears that set.
    Not available on file / database.
    """

    def __init__(self, repository: Repository, names: list[str]) -> None:
        self.repository = repository
        self.names = sorted({str(n) for n in names if n})
        tag_key = "|".join(self.names) or "_"
        self._ns = f"tag:{tag_key}:"

    def _wrap(self) -> Repository:
        return Repository(self.repository.store, prefix=self.repository.prefix + self._ns)

    def get(self, key: str, default: Any = None) -> Any:
        return self._wrap().get(key, default)

    def put(self, key: str, value: Any, seconds: Any = None) -> bool:
        ok = self._wrap().put(key, value, seconds)
        self._remember_key(key)
        return ok

    def forever(self, key: str, value: Any) -> bool:
        ok = self._wrap().forever(key, value)
        self._remember_key(key)
        return ok

    def forget(self, key: str) -> bool:
        return self._wrap().forget(key)

    def flush(self) -> bool:
        meta_key = f"{self.repository.prefix}__tags__:{'|'.join(self.names)}"
        keys = self.repository.store.get(meta_key) or []
        wrapped = self._wrap()
        for key in list(keys):
            wrapped.forget(key)
        self.repository.store.forget(meta_key)
        return True

    def remember(self, key: str, seconds: Any, callback: Callable[[], Any]) -> Any:
        value = self.get(key)
        if value is not None:
            return value
        value = callback()
        self.put(key, value, seconds)
        return value

    def _remember_key(self, key: str) -> None:
        meta_key = f"{self.repository.prefix}__tags__:{'|'.join(self.names)}"
        keys = self.repository.store.get(meta_key) or []
        if key not in keys:
            keys = list(keys) + [key]
            self.repository.store.forever(meta_key, keys)
