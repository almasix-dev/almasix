"""Cache manager + ``Cache`` façade."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from almasix.cache.store import Repository, Store, TaggedCache


class CacheManager:
    """Resolve named cache stores from config."""

    def __init__(self, app: Any | None = None, config: dict[str, Any] | None = None) -> None:
        self.app = app
        self.config = dict(config or {})
        self._stores: dict[str, Repository] = {}
        self._custom: dict[str, Callable[..., Store | Repository]] = {}

    def get_default_driver(self) -> str:
        return str(self.config.get("default") or "array")

    def set_default_driver(self, name: str) -> None:
        self.config["default"] = name

    def extend(self, driver: str, callback: Callable[..., Store | Repository]) -> None:
        """Register a custom driver creator (Laravel ``Cache::extend``)."""
        self._custom[driver] = callback

    def store(self, name: str | None = None) -> Repository:
        key = name or self.get_default_driver()
        if key not in self._stores:
            self._stores[key] = self._resolve(key)
        return self._stores[key]

    def driver(self, name: str | None = None) -> Repository:
        return self.store(name)

    def forget_driver(self, name: str | None = None) -> None:
        if name is None:
            self._stores.clear()
        else:
            self._stores.pop(name, None)

    def _resolve(self, name: str) -> Repository:
        stores = self.config.get("stores") or {}
        cfg = dict(stores.get(name) or {})
        driver = str(cfg.get("driver") or name)
        prefix = str(self.config.get("prefix") or "")

        if driver in self._custom:
            created = self._custom[driver](self.app, cfg, name)
            if isinstance(created, Repository):
                return created
            return Repository(created, prefix=prefix)

        store = self._create_driver(driver, cfg)
        return Repository(store, prefix=prefix)

    def _create_driver(self, driver: str, cfg: dict[str, Any]) -> Store:
        if driver == "array":
            from almasix.cache.drivers.array import ArrayStore

            return ArrayStore()
        if driver == "file":
            from almasix.cache.drivers.file import FileStore

            path = cfg.get("path")
            if path is None and self.app is not None:
                path = Path(self.app.base_path) / "storage" / "framework" / "cache" / "data"
            return FileStore(path or "storage/framework/cache/data")
        if driver == "database":
            from almasix.cache.drivers.database import DatabaseStore
            from almasix.cache.schema import ensure_cache_table_sync

            connection = cfg.get("connection")
            table = str(cfg.get("table") or "cache")
            lock_table = str(cfg.get("lock_table") or "cache_locks")
            ensure_cache_table_sync(connection)
            return DatabaseStore(table=table, lock_table=lock_table, connection=connection)
        if driver == "null":
            from almasix.cache.drivers.array import ArrayStore

            class NullStore(ArrayStore):
                supports_tags = False

                def get(self, key: str) -> Any:
                    del key
                    return None

                def put(self, key: str, value: Any, seconds: int | None) -> bool:
                    del key, value, seconds
                    return True

                def forever(self, key: str, value: Any) -> bool:
                    del key, value
                    return True

                def forget(self, key: str) -> bool:
                    del key
                    return True

                def flush(self) -> bool:
                    return True

                def add(self, key: str, value: Any, seconds: int | None) -> bool:
                    del key, value, seconds
                    return True

                def increment(self, key: str, amount: int = 1) -> int | bool:  # pragma: no cover
                    del key, amount
                    return True

                def decrement(self, key: str, amount: int = 1) -> int | bool:  # pragma: no cover
                    del key, amount
                    return True

            return NullStore()
        if driver == "redis":
            from almasix.cache.drivers.redis import RedisStore

            return RedisStore(connection=cfg.get("connection"))
        raise ValueError(f"Unsupported cache driver: {driver!r}")


class Cache:
    """Static façade — ``Cache.get`` / ``Cache.put`` / …"""

    _manager: CacheManager | None = None

    @classmethod
    def set_manager(cls, manager: CacheManager | None) -> None:
        cls._manager = manager

    @classmethod
    def manager(cls) -> CacheManager:
        if cls._manager is None:
            raise RuntimeError("Cache is not configured. Bootstrap the Application first.")
        return cls._manager

    @classmethod
    def store(cls, name: str | None = None) -> Repository:
        return cls.manager().store(name)

    @classmethod
    def extend(cls, driver: str, callback: Callable[..., Store | Repository]) -> None:
        cls.manager().extend(driver, callback)

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        return cls.store().get(key, default)

    @classmethod
    def many(cls, keys: list[str]) -> dict[str, Any]:
        return cls.store().many(keys)

    @classmethod
    def put(cls, key: str, value: Any, seconds: Any = None) -> bool:
        return cls.store().put(key, value, seconds)

    @classmethod
    def put_many(cls, values: dict[str, Any], seconds: Any = None) -> bool:
        return cls.store().put_many(values, seconds)

    @classmethod
    def forever(cls, key: str, value: Any) -> bool:
        return cls.store().forever(key, value)

    @classmethod
    def forget(cls, key: str) -> bool:
        return cls.store().forget(key)

    @classmethod
    def flush(cls) -> bool:
        return cls.store().flush()

    @classmethod
    def flush_locks(cls) -> bool:
        return cls.store().flush_locks()

    @classmethod
    def has(cls, key: str) -> bool:
        return cls.store().has(key)

    @classmethod
    def missing(cls, key: str) -> bool:
        return cls.store().missing(key)

    @classmethod
    def add(cls, key: str, value: Any, seconds: Any = None) -> bool:
        return cls.store().add(key, value, seconds)

    @classmethod
    def pull(cls, key: str, default: Any = None) -> Any:
        return cls.store().pull(key, default)

    @classmethod
    def touch(cls, key: str, seconds: Any = None) -> bool:
        return cls.store().touch(key, seconds)

    @classmethod
    def remember(cls, key: str, seconds: Any, callback: Any) -> Any:
        return cls.store().remember(key, seconds, callback)

    @classmethod
    def remember_forever(cls, key: str, callback: Any) -> Any:
        return cls.store().remember_forever(key, callback)

    @classmethod
    def increment(cls, key: str, amount: int = 1) -> int | bool:
        return cls.store().increment(key, amount)

    @classmethod
    def decrement(cls, key: str, amount: int = 1) -> int | bool:
        return cls.store().decrement(key, amount)

    @classmethod
    def lock(cls, name: str, seconds: int | None = None, owner: str | None = None) -> Any:
        return cls.store().lock(name, seconds=seconds, owner=owner)

    @classmethod
    def restore_lock(cls, name: str, owner: str) -> Any:
        return cls.store().restore_lock(name, owner)

    @classmethod
    def tags(cls, *names: str) -> TaggedCache:
        return cls.store().tags(*names)

    @classmethod
    def without_overlapping(cls, name: str, callback: Any, seconds: int | None = 86400) -> Any:
        """Run ``callback`` only if the named lock can be acquired."""
        lock = cls.lock(name, seconds=seconds)
        if lock.get() is False:
            return None
        try:
            return callback()
        finally:
            lock.release()
