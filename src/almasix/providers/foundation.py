"""Core framework service provider."""

from __future__ import annotations

from almasix.config import ConfigRepository, set_repository
from almasix.providers.provider import ServiceProvider


class FoundationServiceProvider(ServiceProvider):
    """Binds core framework services into the container."""

    def register(self) -> None:
        from almasix.framework.application import Application
        from almasix.framework.container import Container
        from almasix.http.kernel import HttpKernel
        from almasix.routing.router import Router
        from almasix.translation.provider import TranslationServiceProvider

        app = self.app
        app.container.instance(Application, app)
        app.container.instance(Container, app.container)
        app.container.instance(ConfigRepository, app.config)
        app.container.instance(Router, app.router)
        app.container.instance(HttpKernel, app.http_kernel)
        app.container.singleton("config", lambda c: c.resolve(ConfigRepository))
        # Localization is core infrastructure — register with the foundation.
        TranslationServiceProvider(app).register()
        from almasix.orm.provider import DatabaseServiceProvider
        from almasix.prism.provider import PrismServiceProvider

        DatabaseServiceProvider(app).register()
        PrismServiceProvider(app).register()
        from almasix.auth.provider import AuthServiceProvider
        from almasix.exceptions.provider import ExceptionsServiceProvider
        from almasix.log.provider import LoggingServiceProvider

        AuthServiceProvider(app).register()
        LoggingServiceProvider(app).register()
        ExceptionsServiceProvider(app).register()
        from almasix.console.provider import ConsoleServiceProvider

        ConsoleServiceProvider(app).register()
        from almasix.filesystem.provider import FilesystemServiceProvider
        from almasix.queue.provider import QueueServiceProvider

        FilesystemServiceProvider(app).register()
        from almasix.redis.provider import RedisServiceProvider

        RedisServiceProvider(app).register()
        QueueServiceProvider(app).register()
        from almasix.mail.provider import MailServiceProvider

        MailServiceProvider(app).register()
        from almasix.notifications.provider import NotificationServiceProvider

        NotificationServiceProvider(app).register()
        from almasix.cache.provider import CacheServiceProvider
        from almasix.encryption.provider import EncryptionServiceProvider

        CacheServiceProvider(app).register()
        EncryptionServiceProvider(app).register()
        from almasix.client.provider import ClientServiceProvider
        from almasix.events.provider import EventServiceProvider

        EventServiceProvider(app).register()
        ClientServiceProvider(app).register()

    def boot(self) -> None:
        from almasix.auth.provider import AuthServiceProvider
        from almasix.cache.provider import CacheServiceProvider
        from almasix.client.provider import ClientServiceProvider
        from almasix.console.provider import ConsoleServiceProvider
        from almasix.encryption.provider import EncryptionServiceProvider
        from almasix.events.provider import EventServiceProvider
        from almasix.exceptions.provider import ExceptionsServiceProvider
        from almasix.filesystem.provider import FilesystemServiceProvider
        from almasix.log.provider import LoggingServiceProvider
        from almasix.mail.provider import MailServiceProvider
        from almasix.notifications.provider import NotificationServiceProvider
        from almasix.orm.provider import DatabaseServiceProvider
        from almasix.prism.provider import PrismServiceProvider
        from almasix.queue.provider import QueueServiceProvider
        from almasix.redis.provider import RedisServiceProvider
        from almasix.translation.provider import TranslationServiceProvider

        set_repository(self.app.config)
        TranslationServiceProvider(self.app).boot()
        DatabaseServiceProvider(self.app).boot()
        PrismServiceProvider(self.app).boot()
        AuthServiceProvider(self.app).boot()
        LoggingServiceProvider(self.app).boot()
        ExceptionsServiceProvider(self.app).boot()
        ConsoleServiceProvider(self.app).boot()
        FilesystemServiceProvider(self.app).boot()
        RedisServiceProvider(self.app).boot()
        QueueServiceProvider(self.app).boot()
        MailServiceProvider(self.app).boot()
        NotificationServiceProvider(self.app).boot()
        CacheServiceProvider(self.app).boot()
        EncryptionServiceProvider(self.app).boot()
        EventServiceProvider(self.app).boot()
        ClientServiceProvider(self.app).boot()
