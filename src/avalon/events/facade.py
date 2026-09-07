"""Static ``Event`` façade over :class:`~avalon.events.dispatcher.Dispatcher`."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from avalon.events.dispatcher import Dispatcher, Listener


class Event:
    """App-facing event helpers."""

    _dispatcher: Dispatcher | None = None

    @classmethod
    def set_dispatcher(cls, dispatcher: Dispatcher | None) -> None:
        cls._dispatcher = dispatcher

    @classmethod
    def get_dispatcher(cls) -> Dispatcher:
        if cls._dispatcher is None:
            from avalon.events.helpers import resolve_dispatcher

            cls._dispatcher = resolve_dispatcher()
        return cls._dispatcher

    @classmethod
    def listen(cls, events: str | type | list[str | type], listener: Listener) -> None:
        cls.get_dispatcher().listen(events, listener)

    @classmethod
    def subscribe(cls, subscriber: Any) -> None:
        cls.get_dispatcher().subscribe(subscriber)

    @classmethod
    def dispatch(cls, event: Any, payload: list[Any] | None = None) -> Any:
        return cls.get_dispatcher().dispatch(event, payload)

    @classmethod
    def until(cls, event: Any, payload: list[Any] | None = None) -> Any:
        return cls.get_dispatcher().until(event, payload)

    @classmethod
    def forget(cls, event: str | type) -> None:
        cls.get_dispatcher().forget(event)

    @classmethod
    def flush(cls) -> None:
        cls.get_dispatcher().flush()

    @classmethod
    def has_listeners(cls, event: str | type) -> bool:
        return cls.get_dispatcher().has_listeners(event)

    @classmethod
    def fake(cls, events: list[str | type] | None = None) -> None:
        cls.get_dispatcher().fake(events)

    @classmethod
    def assert_dispatched(
        cls,
        event: str | type,
        callback: Callable[[Any], bool] | None = None,
    ) -> None:
        cls.get_dispatcher().assert_dispatched(event, callback)

    @classmethod
    def assert_not_dispatched(cls, event: str | type) -> None:
        cls.get_dispatcher().assert_not_dispatched(event)

    @classmethod
    def assert_nothing_dispatched(cls) -> None:
        cls.get_dispatcher().assert_nothing_dispatched()
