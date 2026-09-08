"""Queue service provider."""

from __future__ import annotations

from almasix.providers.provider import ServiceProvider
from almasix.queue.dispatcher import Dispatcher
from almasix.queue.helpers import set_dispatcher, set_manager
from almasix.queue.manager import QueueManager


class QueueServiceProvider(ServiceProvider):
    """Binds queue manager and dispatcher from ``config/queue``."""

    def register(self) -> None:
        app = self.app

        def factory(_container):
            config = dict(app.config.get("queue") or {})
            if not config:
                from almasix.queue.helpers import default_queue_config

                db = str(app.config.get("database", {}).get("default") or "default")
                config = default_queue_config(db)
            manager = QueueManager(app, config)
            dispatcher = Dispatcher(manager)
            set_manager(manager)
            set_dispatcher(dispatcher)
            return manager

        app.container.singleton(QueueManager, factory)
        app.container.singleton(Dispatcher, lambda c: Dispatcher(c.resolve(QueueManager)))
        app.container.alias(QueueManager, "queue")

    def boot(self) -> None:
        if self.app.container.bound(QueueManager):
            manager = self.app.make(QueueManager)
            set_manager(manager)
            set_dispatcher(self.app.make(Dispatcher))
