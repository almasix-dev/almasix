"""Redis service provider."""

from __future__ import annotations

from almasix.providers.provider import ServiceProvider
from almasix.redis.facade import Redis
from almasix.redis.helpers import default_redis_config, set_manager
from almasix.redis.manager import RedisManager


class RedisServiceProvider(ServiceProvider):
    """Binds ``RedisManager`` from ``config/redis``."""

    def register(self) -> None:
        app = self.app

        def factory(_container):
            config = dict(app.config.get("redis") or {})
            if not config:
                config = default_redis_config()
            manager = RedisManager(app, config)
            set_manager(manager)
            return manager

        app.container.singleton(RedisManager, factory)
        app.container.alias(RedisManager, "redis")

    def boot(self) -> None:
        if self.app.container.bound(RedisManager):
            manager = self.app.make(RedisManager)
            set_manager(manager)
            Redis.set_manager(manager)
