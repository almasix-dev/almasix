"""What an event says about how it broadcasts.

An event opts in by inheriting `ShouldBroadcast` and naming its channels. Every
other hook — the name on the wire, the payload, whether to broadcast at all —
has a default, so the smallest broadcastable event is a class with one method.
"""

from __future__ import annotations

import inspect
from collections.abc import Sequence
from typing import Any

from almasix.broadcasting.channels import channel_names


class ShouldBroadcast:
    """Marks an event for broadcasting, queued like any other job.

    Subclasses name their channels in `broadcast_on()`; everything else is
    optional:

    - `broadcast_as()` — the name clients listen for (default: the class name)
    - `broadcast_with()` — the payload (default: the public attributes)
    - `broadcast_when()` — whether this instance should go out at all
    - `broadcast_queue` / `broadcast_connection` — where the job is queued
    """

    #: Queue the broadcast job goes on, when it is queued.
    broadcast_queue: str | None = None
    #: Queue connection the broadcast job goes on.
    broadcast_connection: str | None = None

    def broadcast_on(self) -> Any:
        """The channels this event goes out on."""
        return []


class ShouldBroadcastNow(ShouldBroadcast):
    """Broadcast during dispatch instead of going through the queue."""


class ShouldBroadcastAfterCommit(ShouldBroadcast):
    """Hold the broadcast until the surrounding transaction commits.

    Outside a transaction it behaves like `ShouldBroadcast`. Inside one it
    waits, so a rollback takes the broadcast with it.
    """


class InteractsWithSockets:
    """Gives an event the socket that caused it, so it can skip that client.

    `Broadcast.to_others()` and the `broadcast()` helper's `.to_others()` set
    this for you; a controller can also set `event.socket` by hand.
    """

    socket: str | None = None

    def dont_broadcast_to_current_user(self) -> InteractsWithSockets:
        """Leave the current client out — Laravel's `dontBroadcastToCurrentUser`."""
        from almasix.broadcasting.helpers import current_socket_id

        self.socket = current_socket_id()
        return self

    #: Laravel spells this `toOthers()` on the pending broadcast; same thing.
    to_others = dont_broadcast_to_current_user

    def broadcast_to_everyone(self) -> InteractsWithSockets:
        """Undo `to_others()` — everyone hears it, including the sender."""
        self.socket = None
        return self


class InteractsWithBroadcasting:
    """Lets an event choose its broadcast connections at runtime."""

    _broadcast_connection: list[str | None] | None = None

    def broadcast_via(self, connection: str | Sequence[str] | None = None) -> Any:
        """Send over these connections instead of the configured default."""
        if connection is None:
            self._broadcast_connection = [None]
        elif isinstance(connection, str):
            self._broadcast_connection = [connection]
        else:
            self._broadcast_connection = list(connection)
        return self

    def broadcast_connections(self) -> list[str | None]:
        if self._broadcast_connection is None:
            return [None]
        return list(self._broadcast_connection)


def is_broadcastable(event: Any) -> bool:
    """Whether dispatching this event should also broadcast it."""
    if inspect.isclass(event):
        return issubclass(event, ShouldBroadcast)
    return isinstance(event, ShouldBroadcast)


def should_broadcast_now(event: Any) -> bool:
    """Whether the broadcast skips the queue."""
    return isinstance(event, ShouldBroadcastNow)


def broadcast_name(event: Any) -> str:
    """The name clients listen for.

    Laravel defaults to the fully qualified class name; Almasix defaults to
    the bare class name, because Python module paths are not what a JavaScript
    file wants to type. Override `broadcast_as()` to say something else.
    """
    alias = getattr(event, "broadcast_as", None)
    if callable(alias):
        return str(alias())
    return type(event).__name__


def broadcast_channels(event: Any) -> list[str]:
    """The wire names this event is addressed to."""
    channels = getattr(event, "broadcast_on", None)
    return channel_names(channels() if callable(channels) else channels)


def broadcast_payload(event: Any) -> dict[str, Any]:
    """The data that travels with the event.

    `broadcast_with()` wins if the event defines one. Otherwise every public
    attribute is included, models as their serialized form, plus the socket —
    the same shape Laravel builds by reflecting over public properties.
    """
    explicit = getattr(event, "broadcast_with", None)
    if callable(explicit):
        payload = dict(explicit() or {})
    else:
        payload = {
            key: _format(value)
            for key, value in vars(event).items()
            if not key.startswith("_")
        }
    payload.setdefault("socket", getattr(event, "socket", None))
    return payload


def broadcast_allowed(event: Any) -> bool:
    """Whether this particular instance wants to go out."""
    condition = getattr(event, "broadcast_when", None)
    if callable(condition):
        return bool(condition())
    return True


def broadcast_connections(event: Any) -> list[str | None]:
    """The broadcast connections to send over — `[None]` means the default."""
    chooser = getattr(event, "broadcast_connections", None)
    if callable(chooser):
        return list(chooser())
    return [None]


def _format(value: Any) -> Any:
    """A value as it should appear in JSON."""
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if isinstance(value, (list, tuple, set)):
        return [_format(item) for item in value]
    if isinstance(value, dict):
        return {key: _format(item) for key, item in value.items()}
    return value
