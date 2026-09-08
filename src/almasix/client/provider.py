"""HTTP client service provider."""

from __future__ import annotations

from almasix.client.facade import get_factory, set_factory
from almasix.client.factory import Factory
from almasix.providers.provider import ServiceProvider


class ClientServiceProvider(ServiceProvider):
    """Binds the HTTP client factory into the container."""

    def register(self) -> None:
        factory = Factory()
        set_factory(factory)
        self.app.container.instance(Factory, factory)
        self.app.container.instance("http", factory)

    def boot(self) -> None:
        if self.app.container.bound(Factory):
            set_factory(self.app.container.resolve(Factory))
        else:
            set_factory(get_factory())
