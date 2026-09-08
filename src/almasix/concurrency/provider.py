"""Concurrency service provider."""

from __future__ import annotations

from typing import Any

from almasix.concurrency.facade import Concurrency, set_manager
from almasix.concurrency.manager import DEFAULT_DRIVER, ConcurrencyManager
from almasix.providers.provider import ServiceProvider


def default_concurrency_config() -> dict[str, Any]:
    """What an application gets before it writes ``config/concurrency.py``."""
    return {
        "default": DEFAULT_DRIVER,
        "drivers": {
            "thread": {"driver": "thread"},
            "fork": {"driver": "fork"},
            "process": {"driver": "process"},
            "sync": {"driver": "sync"},
        },
    }


class ConcurrencyServiceProvider(ServiceProvider):
    """Binds the concurrency manager from ``config/concurrency``."""

    def register(self) -> None:
        app = self.app

        def factory(_container: Any) -> ConcurrencyManager:
            config = dict(app.config.get("concurrency") or {})
            if not config:
                config = default_concurrency_config()
            manager = ConcurrencyManager(app, config)
            set_manager(manager)
            return manager

        app.container.singleton(ConcurrencyManager, factory)
        app.container.alias(ConcurrencyManager, "concurrency")

    def boot(self) -> None:
        if self.app.container.bound(ConcurrencyManager):
            manager = self.app.make(ConcurrencyManager)
            set_manager(manager)
            Concurrency.set_manager(manager)
