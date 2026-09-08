"""The `Broadcast` façade."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from almasix.broadcasting.broadcasters.base import Broadcaster
from almasix.broadcasting.manager import BroadcastManager, ChannelRoute


class Broadcast:
    """Static access to the broadcast manager (Laravel's `Broadcast` facade)."""

    _manager: BroadcastManager | None = None

    @classmethod
    def set_manager(cls, manager: BroadcastManager | None) -> None:
        cls._manager = manager

    @classmethod
    def manager(cls) -> BroadcastManager:
        if cls._manager is None:
            from almasix.broadcasting.helpers import get_broadcast_manager

            cls._manager = get_broadcast_manager()
        return cls._manager

    # --- connections ---------------------------------------------------

    @classmethod
    def connection(cls, name: str | None = None) -> Broadcaster:
        return cls.manager().connection(name)

    @classmethod
    def driver(cls, name: str | None = None) -> Broadcaster:
        return cls.manager().connection(name)

    @classmethod
    def extend(cls, driver: str, resolver: Any) -> BroadcastManager:
        return cls.manager().extend(driver, resolver)

    @classmethod
    def purge(cls, name: str | None = None) -> None:
        cls.manager().purge(name)

    # --- channels --------------------------------------------------------

    @classmethod
    def channel(
        cls,
        pattern: str,
        callback: Any = None,
        *,
        guards: Sequence[str] | None = None,
    ) -> Any:
        return cls.manager().channel(pattern, callback, guards=guards)

    @classmethod
    def channels(cls) -> list[ChannelRoute]:
        return cls.manager().channels()

    @classmethod
    async def authorize(cls, user: Any, channel: str) -> Any:
        return await cls.manager().authorize(user, channel)

    @classmethod
    async def auth(cls, request: Any) -> dict[str, Any]:
        return await cls.manager().auth(request)

    # --- sending ---------------------------------------------------------

    @classmethod
    async def event(
        cls,
        channels: Any,
        event: str,
        payload: Mapping[str, Any] | None = None,
        *,
        socket: str | None = None,
        connection: str | None = None,
    ) -> None:
        """Broadcast without an event class — a name and a payload."""
        await cls.manager().event(
            channels,
            event,
            payload,
            socket=socket,
            connection=connection,
        )

    @classmethod
    async def send(cls, event: Any, *, connection: str | None = None) -> None:
        """Broadcast a `ShouldBroadcast` event immediately, skipping the queue."""
        await cls.manager().broadcast_event(event, connection=connection)

    @classmethod
    def queue(cls, event: Any) -> None:
        """Hand a `ShouldBroadcast` event to the queue — what dispatch does."""
        cls.manager().queue(event)

    # --- testing ---------------------------------------------------------

    @classmethod
    def fake(cls) -> Any:
        """Swap every connection for a recorder and return it."""
        from almasix.broadcasting.testing import FakeBroadcaster

        fake = FakeBroadcaster()
        manager = cls.manager()
        manager.purge()
        manager.extend("__fake__", lambda name, config: fake)
        for name in list(manager.config.get("connections") or {}):
            manager.set_connection(name, fake)
        manager.set_connection(manager.get_default_driver(), fake)
        return fake
