"""Broadcasting under test — record instead of send, then assert."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from almasix.broadcasting.broadcasters.base import Broadcaster


@dataclass
class RecordedBroadcast:
    """One broadcast that would have gone out."""

    event: str
    channels: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    socket: str | None = None

    def on(self, channel: str) -> bool:
        return channel in self.channels


class FakeBroadcaster(Broadcaster):
    """Records broadcasts and answers questions about them.

    Installed by `Broadcast.fake()`, which points every configured connection
    at one recorder, so a test does not have to know which connection the
    code under test picked.
    """

    driver = "fake"

    def __init__(self, name: str = "fake", config: Mapping[str, Any] | None = None) -> None:
        super().__init__(name, config or {"key": "almasix", "secret": "fake-secret"})
        self.broadcasts: list[RecordedBroadcast] = []

    async def broadcast(
        self,
        channels: Sequence[str],
        event: str,
        payload: Mapping[str, Any],
        *,
        socket: str | None = None,
    ) -> None:
        self.broadcasts.append(
            RecordedBroadcast(
                event=event,
                channels=list(channels),
                payload=dict(payload),
                socket=socket,
            )
        )

    # ------------------------------------------------------------------
    # Assertions

    def recorded(
        self,
        event: str | type | None = None,
        callback: Callable[[RecordedBroadcast], bool] | None = None,
    ) -> list[RecordedBroadcast]:
        name = _name_of(event)
        found = [record for record in self.broadcasts if name is None or record.event == name]
        if callback is not None:
            found = [record for record in found if callback(record)]
        return found

    def assert_broadcast(
        self,
        event: str | type,
        callback: Callable[[RecordedBroadcast], bool] | None = None,
    ) -> None:
        name = _name_of(event)
        if not self.recorded(event):
            sent = ", ".join(sorted({record.event for record in self.broadcasts})) or "nothing"
            raise AssertionError(f"Event [{name}] was not broadcast. Broadcast: {sent}.")
        if callback is not None and not self.recorded(event, callback):
            raise AssertionError(f"Event [{name}] was broadcast, but not as expected.")

    def assert_broadcast_on(self, event: str | type, channel: str) -> None:
        name = _name_of(event)
        if not self.recorded(event, lambda record: record.on(channel)):
            raise AssertionError(f"Event [{name}] was not broadcast on channel [{channel}].")

    def assert_not_broadcast(self, event: str | type) -> None:
        if self.recorded(event):
            raise AssertionError(f"Event [{_name_of(event)}] was broadcast unexpectedly.")

    def assert_nothing_broadcast(self) -> None:
        if self.broadcasts:
            names = ", ".join(record.event for record in self.broadcasts)
            raise AssertionError(f"Expected no broadcasts; got: {names}.")

    def assert_broadcast_count(self, count: int) -> None:
        if len(self.broadcasts) != count:
            raise AssertionError(f"Expected {count} broadcasts; got {len(self.broadcasts)}.")

    def flush(self) -> None:
        self.broadcasts.clear()


def _name_of(event: str | type | None) -> str | None:
    """Accept either the wire name or the event class."""
    if event is None or isinstance(event, str):
        return event
    alias = getattr(event, "broadcast_as", None)
    if callable(alias):
        try:
            # A `broadcast_as` that needs no instance (static or class method)
            # can answer for the class; a plain method cannot, and the class
            # name is the default anyway.
            return str(alias())
        except TypeError:
            pass
    return event.__name__
