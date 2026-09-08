"""One door to every fake the framework ships.

Laravel spreads its fakes across façades — `Mail::fake()`, `Queue::fake()`,
`Http::fake()`. Almasix keeps those spellings and adds one place that knows
them all, so a test can say `fake("mail", "queue")` and a teardown can put
everything back without naming each surface.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

#: Every surface that can be faked, and how.
_FAKES: dict[str, Callable[[], Any]] = {}


def _register() -> None:
    if _FAKES:
        return

    def mail() -> Any:
        from almasix.mail import Mail

        return Mail.fake()

    def queue() -> Any:
        from almasix.queue.testing import fake_queue

        return fake_queue()

    def notification() -> Any:
        from almasix.notifications.testing import fake_notifications

        return fake_notifications()

    def event() -> Any:
        from almasix.events import Event

        return Event.fake()

    def http() -> Any:
        from almasix.client.facade import Http

        return Http.fake()

    def process() -> Any:
        from almasix.process.facade import Process

        return Process.fake()

    def storage() -> Any:
        from almasix.filesystem.testing import fake_disk

        return fake_disk()

    def broadcast() -> Any:
        from almasix.broadcasting import Broadcast

        return Broadcast.fake()

    def scout() -> Any:
        from almasix.scout import Scout

        return Scout.fake()

    _FAKES.update(
        {
            "mail": mail,
            "queue": queue,
            "notification": notification,
            "event": event,
            "http": http,
            "process": process,
            "storage": storage,
            "broadcast": broadcast,
            "scout": scout,
        }
    )


def fake(surface: str) -> Any:
    """Fake one surface by name, and hand back whatever asserts on it."""
    _register()
    if surface not in _FAKES:
        raise ValueError(f"There is no fake for [{surface}]. Try one of: {', '.join(fakeable())}.")
    return _FAKES[surface]()


def fakeable() -> list[str]:
    """The surfaces `fake()` knows about."""
    _register()
    return sorted(_FAKES)


def restore_fakes() -> None:
    """Put every faked surface back the way it was.

    A test that fakes something and then fails would otherwise leave the fake
    installed for whatever runs next; call this from a fixture's teardown.
    """
    from almasix.client.facade import set_factory as set_http_factory
    from almasix.events import Event
    from almasix.notifications.helpers import set_sender
    from almasix.process.facade import set_factory as set_process_factory
    from almasix.queue.helpers import set_dispatcher

    set_http_factory(None)
    set_process_factory(None)
    set_dispatcher(None)
    set_sender(None)
    Event.set_dispatcher(None)

    from almasix.broadcasting import Broadcast
    from almasix.scout import Scout

    Broadcast.set_manager(None)
    Scout.set_manager(None)
