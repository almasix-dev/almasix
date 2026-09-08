"""Search service provider."""

from __future__ import annotations

from typing import Any

from almasix.providers.provider import ServiceProvider
from almasix.scout.facade import Scout
from almasix.scout.helpers import default_scout_config, set_engine_manager
from almasix.scout.manager import EngineManager


class ScoutServiceProvider(ServiceProvider):
    """Binds the engine manager and teaches queries how to index themselves."""

    def register(self) -> None:
        app = self.app

        def factory(_container: Any) -> EngineManager:
            config = dict(app.config.get("scout") or {})
            if not config:
                config = default_scout_config()
            manager = EngineManager(app, config)
            set_engine_manager(manager)
            return manager

        app.container.singleton(EngineManager, factory)
        app.container.alias(EngineManager, "scout")

    def boot(self) -> None:
        if not self.app.container.bound(EngineManager):
            return
        manager = self.app.make(EngineManager)
        set_engine_manager(manager)
        Scout.set_manager(manager)

        from almasix.scout import macros

        macros.install()
