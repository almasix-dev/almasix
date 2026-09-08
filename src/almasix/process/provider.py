"""Process service provider."""

from __future__ import annotations

from almasix.process.facade import get_factory, set_factory
from almasix.process.factory import Factory
from almasix.providers.provider import ServiceProvider


class ProcessServiceProvider(ServiceProvider):
    """Binds the process factory into the container."""

    def register(self) -> None:
        factory = Factory()
        set_factory(factory)
        self.app.container.instance(Factory, factory)
        self.app.container.instance("process", factory)

    def boot(self) -> None:
        if self.app.container.bound(Factory):
            set_factory(self.app.container.resolve(Factory))
        else:
            set_factory(get_factory())
