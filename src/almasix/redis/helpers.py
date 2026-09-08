"""``redis()`` helper and default config."""

from __future__ import annotations

from typing import Any

from almasix.redis.facade import Redis
from almasix.redis.manager import RedisManager

_manager: RedisManager | None = None


def set_manager(manager: RedisManager | None) -> None:
    global _manager
    _manager = manager
    Redis.set_manager(manager)


def get_manager() -> RedisManager:
    if _manager is None:
        raise RuntimeError("Redis is not configured. Bootstrap the Application first.")
    return _manager


def redis(name: str | None = None) -> Any:
    """Return the named async Redis client (default connection when omitted)."""
    return get_manager().connection(name)


def default_redis_config() -> dict[str, Any]:
    """Default ``config/redis.py`` shape."""
    from almasix.config import env

    return {
        "default": env("REDIS_CLIENT", "default"),
        "connections": {
            "default": {
                "url": env("REDIS_URL"),
                "host": env("REDIS_HOST", "127.0.0.1"),
                "port": int(env("REDIS_PORT", 6379) or 6379),
                "database": int(env("REDIS_DB", 0) or 0),
                "password": env("REDIS_PASSWORD"),
                "username": env("REDIS_USERNAME"),
            },
        },
    }
