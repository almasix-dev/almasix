"""Cache stores."""

from almasix.config import env

config = {
    "default": env("CACHE_STORE", "file"),
    # Optional dedicated store for RateLimiter / throttle (Laravel `limiter`).
    "limiter": env("CACHE_LIMITER_STORE", None),
    "prefix": env("CACHE_PREFIX", "almasix_cache_"),
    "stores": {
        "array": {"driver": "array"},
        "file": {
            "driver": "file",
            "path": "storage/framework/cache/data",
        },
        "database": {
            "driver": "database",
            "connection": None,
            "table": "cache",
            "lock_table": "cache_locks",
        },
        "redis": {
            "driver": "redis",
            "connection": env("REDIS_CACHE_CONNECTION", "default"),
        },
        "null": {"driver": "null"},
    },
}
