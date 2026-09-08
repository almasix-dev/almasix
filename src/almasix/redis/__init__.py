"""Redis connections and façade — optional ``almasix[redis]`` extra."""

from __future__ import annotations

from almasix.redis.facade import Redis
from almasix.redis.helpers import default_redis_config, get_manager, redis, set_manager
from almasix.redis.manager import RedisManager, require_redis
from almasix.redis.provider import RedisServiceProvider

__all__ = [
    "Redis",
    "RedisManager",
    "RedisServiceProvider",
    "default_redis_config",
    "get_manager",
    "redis",
    "require_redis",
    "set_manager",
]
