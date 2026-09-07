"""Events service provider."""

from __future__ import annotations

from typing import ClassVar

from avalon.events.dispatcher import Dispatcher
from avalon.events.facade import Event
from avalon.events.helpers import set_dispatcher
from avalon.providers.provider import ServiceProvider


class EventServiceProvider(ServiceProvider):
    """Binds the application :class:`Dispatcher`."""

    listen: ClassVar[dict[str | type, list]] = {}

    def register(self) -> None:
        app = self.app

        def factory(_container):
            dispatcher = Dispatcher(app.container)
            set_dispatcher(dispatcher)
            return dispatcher

        app.container.singleton(Dispatcher, factory)
        app.container.alias(Dispatcher, "events")

    def boot(self) -> None:
        if self.app.container.bound(Dispatcher):
            dispatcher = self.app.make(Dispatcher)
            set_dispatcher(dispatcher)
            Event.set_dispatcher(dispatcher)
            for event, listeners in (self.listen or {}).items():
                for listener in listeners:
                    dispatcher.listen(event, listener)
