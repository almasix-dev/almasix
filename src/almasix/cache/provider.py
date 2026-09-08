"""Cache service provider."""

from __future__ import annotations

from almasix.cache.helpers import default_cache_config, set_manager
from almasix.cache.manager import Cache, CacheManager
from almasix.providers.provider import ServiceProvider


class CacheServiceProvider(ServiceProvider):
    """Binds Cache manager from ``config/cache``."""

    def register(self) -> None:
        app = self.app

        def factory(_container):
            config = dict(app.config.get("cache") or {})
            if not config:
                config = default_cache_config(app.base_path)
            manager = CacheManager(app, config)
            set_manager(manager)
            return manager

        app.container.singleton(CacheManager, factory)
        app.container.alias(CacheManager, "cache")

    def boot(self) -> None:
        if self.app.container.bound(CacheManager):
            manager = self.app.make(CacheManager)
            set_manager(manager)
            Cache.set_manager(manager)
