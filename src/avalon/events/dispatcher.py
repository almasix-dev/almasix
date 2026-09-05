"""Application event dispatcher — listen / subscribe / dispatch."""

from __future__ import annotations

import fnmatch
import inspect
from collections.abc import Callable
from typing import Any

from avalon.events.queued import is_should_queue, queue_listener

Listener = Callable[..., Any] | type | str


class Dispatcher:
    """Sync event bus with wildcard listeners and queued listener support."""

    def __init__(self, container: Any | None = None) -> None:
        self._container = container
        self._listeners: dict[str, list[Listener]] = {}
        self._wildcards: list[tuple[str, Listener]] = []
        self._faking = False
        self._fake_events: list[Any] = []
        self._fake_names: set[str] | None = None

    def set_container(self, container: Any | None) -> None:
        self._container = container

    def listen(self, events: str | type | list[str | type], listener: Listener) -> None:
        names = self._normalize_events(events)
        for name in names:
            if "*" in name:
                self._wildcards.append((name, listener))
            else:
                self._listeners.setdefault(name, []).append(listener)

    def subscribe(self, subscriber: Any) -> None:
        instance = self._resolve(subscriber)
        if not hasattr(instance, "subscribe"):
            raise TypeError(f"{type(instance).__name__} has no subscribe() method")
        instance.subscribe(self)

    def forget(self, event: str | type) -> None:
        name = self._event_name(event)
        self._listeners.pop(name, None)
        self._wildcards = [(p, lst) for p, lst in self._wildcards if p != name]

    def flush(self) -> None:
        self._listeners.clear()
        self._wildcards.clear()

    def has_listeners(self, event: str | type) -> bool:
        name = self._event_name(event)
        if self._listeners.get(name):
            return True
        return any(fnmatch.fnmatchcase(name, pattern) for pattern, _ in self._wildcards)

    def get_listeners(self, event: str | type | None = None) -> dict[str, list[Listener]]:
        if event is None:
            out = {k: list(v) for k, v in self._listeners.items()}
            for pattern, listener in self._wildcards:
                out.setdefault(pattern, []).append(listener)
            return out
        name = self._event_name(event)
        return {name: self._collect(name)}

    def dispatch(self, event: Any, payload: list[Any] | None = None, *, halt: bool = False) -> Any:
        if self._should_fake(event):
            self._fake_events.append(event)
            return None

        name = self._event_name(event)
        responses: list[Any] = []
        for listener in self._collect(name):
            response = self._invoke(listener, event, payload, name)
            if response is False:
                break
            if halt and response is not None:
                return response
            responses.append(response)
        return None if halt else responses

    def until(self, event: Any, payload: list[Any] | None = None) -> Any:
        return self.dispatch(event, payload, halt=True)

    def fake(self, events: list[str | type] | None = None) -> None:
        self._faking = True
        self._fake_names = None if events is None else {self._event_name(e) for e in events}
        self._fake_events = []

    def assert_dispatched(
        self,
        event: str | type,
        callback: Callable[[Any], bool] | None = None,
    ) -> None:
        name = self._event_name(event)
        matches = [e for e in self._fake_events if self._event_name(e) == name]
        if not matches:
            raise AssertionError(f"Event {name!r} was not dispatched.")
        if callback is not None and not any(callback(e) for e in matches):
            raise AssertionError(f"Event {name!r} failed the assertion callback.")

    def assert_not_dispatched(self, event: str | type) -> None:
        name = self._event_name(event)
        if any(self._event_name(e) == name for e in self._fake_events):
            raise AssertionError(f"Event {name!r} was dispatched unexpectedly.")

    def assert_nothing_dispatched(self) -> None:
        if self._fake_events:
            raise AssertionError(f"Expected no events; got {len(self._fake_events)}.")

    def dispatched(self) -> list[Any]:
        return list(self._fake_events)

    def _should_fake(self, event: Any) -> bool:
        if not self._faking:
            return False
        if self._fake_names is None:
            return True
        return self._event_name(event) in self._fake_names

    def _collect(self, name: str) -> list[Listener]:
        found = list(self._listeners.get(name, []))
        for pattern, listener in self._wildcards:
            if fnmatch.fnmatchcase(name, pattern):
                found.append(listener)
        return found

    def _invoke(
        self,
        listener: Listener,
        event: Any,
        payload: list[Any] | None,
        name: str,
    ) -> Any:
        # Wildcard listeners receive (event_name, payload_list)
        is_wildcard_call = payload is not None or any(
            fnmatch.fnmatchcase(name, p) for p, lst in self._wildcards if lst is listener
        )

        if inspect.isclass(listener) or isinstance(listener, str):
            resolved = self._resolve(listener)
            return self._invoke_object(resolved, listener, event, payload, name, is_wildcard_call)

        if callable(listener):
            if is_wildcard_call and payload is not None:
                return listener(name, payload)
            if is_wildcard_call and any(
                fnmatch.fnmatchcase(name, p) for p, lst in self._wildcards if lst is listener
            ):
                return listener(name, [event] if payload is None else payload)
            return listener(event)

        return self._invoke_object(listener, type(listener), event, payload, name, is_wildcard_call)

    def _invoke_object(
        self,
        resolved: Any,
        original: Any,
        event: Any,
        payload: list[Any] | None,
        name: str,
        is_wildcard_call: bool,
    ) -> Any:
        method = getattr(resolved, "handle", None)
        if method is None and callable(resolved):
            method = resolved
        if method is None:
            raise TypeError(f"Listener {original!r} is not callable and has no handle()")

        should_queue = is_should_queue(resolved) or is_should_queue(original)
        if should_queue:
            if (
                hasattr(resolved, "should_queue")
                and callable(resolved.should_queue)
                and not resolved.should_queue(event)
            ):
                return method(event)
            queue_listener(resolved, event, method="handle")
            return None

        if is_wildcard_call and payload is not None:
            try:
                return method(name, payload)
            except TypeError:
                pass
        return method(event)

    def _resolve(self, listener: Listener) -> Any:
        if inspect.isclass(listener):
            if self._container is not None and hasattr(self._container, "make"):
                try:
                    return self._container.make(listener)
                except Exception:  # noqa: BLE001
                    return listener()
            return listener()
        if isinstance(listener, str):
            return self._resolve(_import_symbol(listener))
        return listener

    def _normalize_events(self, events: str | type | list[str | type]) -> list[str]:
        if isinstance(events, list):
            return [self._event_name(e) for e in events]
        return [self._event_name(events)]

    def _event_name(self, event: Any) -> str:
        if isinstance(event, str):
            return event
        if inspect.isclass(event):
            return f"{event.__module__}.{event.__qualname__}"
        return f"{type(event).__module__}.{type(event).__qualname__}"


def _import_symbol(path: str) -> Any:
    module_path, _, name = path.rpartition(".")
    if not module_path:
        raise ImportError(f"Invalid listener path: {path}")
    import importlib

    return getattr(importlib.import_module(module_path), name)
