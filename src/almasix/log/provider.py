"""Logging service provider."""

from __future__ import annotations

from almasix.log.manager import LogManager, set_log_manager
from almasix.providers.provider import ServiceProvider


class LoggingServiceProvider(ServiceProvider):
    """Binds ``LogManager`` and installs the process-wide manager."""

    def register(self) -> None:
        app = self.app
        app.container.singleton(LogManager, lambda _c: LogManager(app))
        app.container.alias(LogManager, "log")

    def boot(self) -> None:
        set_log_manager(self.app.make(LogManager))
