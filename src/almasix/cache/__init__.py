"""Laravel-shaped Cache — stores, locks, and ``cache()`` helper."""

from __future__ import annotations

from almasix.cache.helpers import cache, default_cache_config, get_manager, set_manager
from almasix.cache.locks import CacheLock, DatabaseLock, FileLock, LockTimeoutError
from almasix.cache.manager import Cache, CacheManager
from almasix.cache.provider import CacheServiceProvider
from almasix.cache.schema import ensure_cache_table, ensure_cache_table_sync
from almasix.cache.store import Repository, TaggedCache

__all__ = [
    "Cache",
    "CacheLock",
    "CacheManager",
    "CacheServiceProvider",
    "DatabaseLock",
    "FileLock",
    "LockTimeoutError",
    "Repository",
    "TaggedCache",
    "cache",
    "default_cache_config",
    "ensure_cache_table",
    "ensure_cache_table_sync",
    "get_manager",
    "set_manager",
]
