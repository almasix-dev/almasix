"""Core framework service provider."""

from __future__ import annotations

from avalon.config import ConfigRepository, set_repository
from avalon.providers.provider import ServiceProvider


class FoundationServiceProvider(ServiceProvider):
    """Binds core framework services into the container."""

    def register(self) -> None:
        from avalon.framework.application import Application
        from avalon.framework.container import Container
        from avalon.http.kernel import HttpKernel
        from avalon.routing.router import Router
        from avalon.translation.provider import TranslationServiceProvider

        app = self.app
        app.container.instance(Application, app)
        app.container.instance(Container, app.container)
        app.container.instance(ConfigRepository, app.config)
        app.container.instance(Router, app.router)
        app.container.instance(HttpKernel, app.http_kernel)
        app.container.singleton("config", lambda c: c.resolve(ConfigRepository))
        # Localization is core infrastructure — register with the foundation.
        TranslationServiceProvider(app).register()
        from avalon.caliburn.provider import CaliburnServiceProvider
        from avalon.orm.provider import DatabaseServiceProvider

        DatabaseServiceProvider(app).register()
        CaliburnServiceProvider(app).register()
        from avalon.auth.provider import AuthServiceProvider
        from avalon.exceptions.provider import ExceptionsServiceProvider
        from avalon.log.provider import LoggingServiceProvider

        AuthServiceProvider(app).register()
        LoggingServiceProvider(app).register()
        ExceptionsServiceProvider(app).register()
        from avalon.console.provider import ConsoleServiceProvider

        ConsoleServiceProvider(app).register()
        from avalon.filesystem.provider import FilesystemServiceProvider
        from avalon.queue.provider import QueueServiceProvider

        FilesystemServiceProvider(app).register()
        from avalon.redis.provider import RedisServiceProvider

        RedisServiceProvider(app).register()
        QueueServiceProvider(app).register()
        from avalon.mail.provider import MailServiceProvider

        MailServiceProvider(app).register()
        from avalon.notifications.provider import NotificationServiceProvider

        NotificationServiceProvider(app).register()
        from avalon.cache.provider import CacheServiceProvider
        from avalon.encryption.provider import EncryptionServiceProvider

        CacheServiceProvider(app).register()
        EncryptionServiceProvider(app).register()

    def boot(self) -> None:
        from avalon.auth.provider import AuthServiceProvider
        from avalon.cache.provider import CacheServiceProvider
        from avalon.caliburn.provider import CaliburnServiceProvider
        from avalon.console.provider import ConsoleServiceProvider
        from avalon.encryption.provider import EncryptionServiceProvider
        from avalon.exceptions.provider import ExceptionsServiceProvider
        from avalon.filesystem.provider import FilesystemServiceProvider
        from avalon.log.provider import LoggingServiceProvider
        from avalon.mail.provider import MailServiceProvider
        from avalon.notifications.provider import NotificationServiceProvider
        from avalon.queue.provider import QueueServiceProvider
        from avalon.redis.provider import RedisServiceProvider
        from avalon.orm.provider import DatabaseServiceProvider
        from avalon.translation.provider import TranslationServiceProvider

        set_repository(self.app.config)
        TranslationServiceProvider(self.app).boot()
        DatabaseServiceProvider(self.app).boot()
        CaliburnServiceProvider(self.app).boot()
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
