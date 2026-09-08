"""Cache helpers + default config."""

from __future__ import annotations

from typing import Any

from almasix.cache.manager import Cache, CacheManager

_manager: CacheManager | None = None


def set_manager(manager: CacheManager | None) -> None:
    global _manager
    _manager = manager
    Cache.set_manager(manager)


def get_manager() -> CacheManager:
    if _manager is None:
        raise RuntimeError("Cache is not configured. Bootstrap the Application first.")
    return _manager


def cache(key: str | None = None, default: Any = None) -> Any:
    """Laravel ``cache()`` helper.

    - ``cache()`` → default store repository
    - ``cache('key')`` → get
    - ``cache({'k': 'v'}, seconds)`` is not used; prefer ``Cache.put``
    """
    store = get_manager().store()
    if key is None:
        return store
    if isinstance(key, dict):
        # ``cache({'key': value}, ttl)`` — second arg via default as TTL when int-like
        ttl = default
        for item_key, value in key.items():
            store.put(item_key, value, ttl)
        return True
    return store.get(key, default)


def default_cache_config(base_path: str | Any = ".") -> dict[str, Any]:
    from pathlib import Path

    root = Path(base_path)
    return {
        "default": "array",
        "prefix": "almasix_cache_",
        "stores": {
            "array": {"driver": "array"},
            "file": {
                "driver": "file",
                "path": str(root / "storage" / "framework" / "cache" / "data"),
            },
            "database": {
                "driver": "database",
                "connection": None,
                "table": "cache",
                "lock_table": "cache_locks",
            },
            "null": {"driver": "null"},
            "redis": {
                "driver": "redis",
                "connection": "default",
            },
        },
    }
