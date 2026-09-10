"""The Sonar socket hub — who is connected, and what they are listening to.

This is the in-process half of Almasix's first-party realtime server (Sonar).
It knows nothing about HTTP or FastAPI: connections arrive as an id and a
callable that delivers a frame, which is what makes the hub testable without
a browser.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from almasix.broadcasting.channels import is_presence

Sender = Callable[[dict[str, Any]], Awaitable[None]]


def new_socket_id() -> str:
    """A fresh connection id, in Pusher's `123456.7890123` shape."""
    return f"{secrets.randbelow(900000) + 100000}.{secrets.randbelow(9000000) + 1000000}"


@dataclass
class Connection:
    """One live client."""

    id: str
    send: Sender
    channels: set[str] = field(default_factory=set)
    #: Presence information per channel, as the client proved it.
    members: dict[str, dict[str, Any]] = field(default_factory=dict)
    user: Any = None


class SocketHub:
    """Routes frames between connections and channels.

    Every method is safe to call for a connection that has gone away — a
    browser closing mid-broadcast is normal, not an error.
    """

    def __init__(self) -> None:
        self._connections: dict[str, Connection] = {}
        self._channels: dict[str, set[str]] = {}

    # ------------------------------------------------------------------
    # Connections

    def connect(self, send: Sender, *, socket_id: str | None = None) -> Connection:
        connection = Connection(id=socket_id or new_socket_id(), send=send)
        self._connections[connection.id] = connection
        return connection

    async def disconnect(self, connection: Connection) -> None:
        """Drop a connection and tell the presence channels it left."""
        for channel in list(connection.channels):
            await self.unsubscribe(connection, channel)
        self._connections.pop(connection.id, None)

    def connection(self, socket_id: str) -> Connection | None:
        return self._connections.get(socket_id)

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    # ------------------------------------------------------------------
    # Subscriptions

    async def subscribe(
        self,
        connection: Connection,
        channel: str,
        member: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Add a connection to a channel; return the presence roster.

        On a presence channel the members already there are announced to the
        newcomer, and the newcomer is announced to them.
        """
        subscribers = self._channels.setdefault(channel, set())
        roster = self.members(channel)
        subscribers.add(connection.id)
        connection.channels.add(channel)

        if is_presence(channel) and member is not None:
            connection.members[channel] = dict(member)
            await self.publish(
                [channel],
                "almasix:member_added",
                dict(member),
                socket=connection.id,
            )
        return roster

    async def unsubscribe(self, connection: Connection, channel: str) -> None:
        subscribers = self._channels.get(channel)
        if subscribers is not None:
            subscribers.discard(connection.id)
            if not subscribers:
                self._channels.pop(channel, None)
        connection.channels.discard(channel)

        member = connection.members.pop(channel, None)
        if member is not None:
            await self.publish([channel], "almasix:member_removed", member, socket=connection.id)

    def members(self, channel: str) -> list[dict[str, Any]]:
        """Everyone currently on a presence channel."""
        roster: list[dict[str, Any]] = []
        for socket_id in self._channels.get(channel, set()):
            connection = self._connections.get(socket_id)
            if connection is not None and channel in connection.members:
                roster.append(dict(connection.members[channel]))
        return roster

    def channels(self) -> dict[str, int]:
        """Every occupied channel and how many connections are on it."""
        return {name: len(sockets) for name, sockets in sorted(self._channels.items())}

    def subscribers(self, channel: str) -> list[Connection]:
        return [
            connection
            for socket_id in self._channels.get(channel, set())
            if (connection := self._connections.get(socket_id)) is not None
        ]

    # ------------------------------------------------------------------
    # Delivery

    async def publish(
        self,
        channels: Iterable[str],
        event: str,
        payload: Any,
        *,
        socket: str | None = None,
    ) -> int:
        """Deliver a frame; return how many connections received it.

        A connection whose send fails is dropped rather than allowed to break
        the broadcast for everyone else.
        """
        delivered = 0
        dead: list[Connection] = []
        for channel in channels:
            frame = {"event": event, "channel": channel, "data": payload}
            for connection in self.subscribers(channel):
                if socket is not None and connection.id == socket:
                    continue
                try:
                    await connection.send(frame)
                except Exception:
                    dead.append(connection)
                else:
                    delivered += 1
        for connection in dead:
            await self.disconnect(connection)
        return delivered

    def flush(self) -> None:
        """Forget everything — between tests, mostly."""
        self._connections.clear()
        self._channels.clear()


_hub: SocketHub | None = None


def get_hub() -> SocketHub:
    """The process-wide hub, created on first use.

    The socket endpoint and the websocket broadcaster have to be looking at
    the same connections, and one of them is reached through the container
    while the other is reached through a route — so the hub lives here.
    """
    global _hub
    if _hub is None:
        _hub = SocketHub()
    return _hub


def set_hub(hub: SocketHub | None) -> None:
    global _hub
    _hub = hub


def decode_frame(raw: str | bytes) -> dict[str, Any]:
    """A client frame as a dict, whatever nonsense arrived."""
    try:
        frame = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return frame if isinstance(frame, dict) else {}
