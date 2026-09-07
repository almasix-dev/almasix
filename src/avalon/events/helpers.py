"""Functional event helpers."""

from __future__ import annotations

from typing import Any

from avalon.events.dispatcher import Dispatcher, Listener
from avalon.events.facade import Event

_dispatcher: Dispatcher | None = None


def set_dispatcher(dispatcher: Dispatcher | None) -> None:
    global _dispatcher
    _dispatcher = dispatcher
    Event.set_dispatcher(dispatcher)


def get_dispatcher() -> Dispatcher:
    return Event.get_dispatcher()


def resolve_dispatcher() -> Dispatcher:
    if _dispatcher is not None:
        return _dispatcher
    return Dispatcher()


def listen(events: str | type | list[str | type], listener: Listener) -> None:
    Event.listen(events, listener)


def event(event_obj: Any, payload: list[Any] | None = None) -> Any:
    """Dispatch an event (Laravel ``event()`` helper)."""
    return Event.dispatch(event_obj, payload)


def dispatch(event_obj: Any, payload: list[Any] | None = None) -> Any:
    return Event.dispatch(event_obj, payload)
