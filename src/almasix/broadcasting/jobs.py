"""Getting a broadcast off the request and onto the queue."""

from __future__ import annotations

import asyncio
from typing import Any

from almasix.broadcasting.events import (
    ShouldBroadcastAfterCommit,
    broadcast_allowed,
    broadcast_channels,
    broadcast_connections,
    broadcast_name,
    broadcast_payload,
    should_broadcast_now,
)
from almasix.queue.job import Job, ShouldQueue


class BroadcastEvent(Job, ShouldQueue):
    """The queued half of a broadcast.

    The event's channels and payload are worked out when the job is created,
    not when it runs, so what gets stored on the queue is plain JSON and any
    queue driver can carry it.
    """

    def __init__(
        self,
        channels: list[str],
        event: str,
        payload: dict[str, Any],
        socket: str | None = None,
        connections: list[str | None] | None = None,
        *,
        connection: str | None = None,
        queue: str | bool = "default",
    ) -> None:
        self.channels = list(channels)
        self.event = event
        self.payload = dict(payload)
        self.socket = socket
        self.connections = list(connections or [None])
        if connection is not None:
            self.connection = connection
        self.queue = queue

    async def handle(self) -> None:
        from almasix.broadcasting.helpers import get_broadcast_manager

        manager = get_broadcast_manager()
        for target in self.connections:
            await manager.event(
                self.channels,
                self.event,
                self.payload,
                socket=self.socket,
                connection=target,
            )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"BroadcastEvent({self.event!r} on {self.channels!r})"


def job_for(event: Any) -> BroadcastEvent:
    """The queue job that will broadcast this event."""
    return BroadcastEvent(
        broadcast_channels(event),
        broadcast_name(event),
        broadcast_payload(event),
        getattr(event, "socket", None),
        broadcast_connections(event),
        connection=getattr(event, "broadcast_connection", None),
        queue=getattr(event, "broadcast_queue", None) or "default",
    )


def queue_broadcast(event: Any) -> None:
    """Broadcast an event — now if it asked for now, otherwise on the queue.

    Called from the synchronous event dispatcher, which is why the async work
    is bridged here rather than made the caller's problem.
    """
    if not broadcast_allowed(event) or not broadcast_channels(event):
        return

    if isinstance(event, ShouldBroadcastAfterCommit) and _defer_until_commit(event):
        return

    _send_now(event)


def _defer_until_commit(event: Any) -> bool:
    """Park the broadcast on the current transaction; say whether we did.

    `False` means there was no transaction to wait for, and the caller should
    broadcast as usual.
    """
    try:
        from almasix.orm.facade import get_manager

        connection = get_manager().connection(getattr(event, "broadcast_database", None))
    except Exception:  # noqa: BLE001 — an application without a database still broadcasts
        return False
    if not connection.in_transaction():
        return False

    connection.after_commit(lambda: _send_now(event))
    return True


def _send_now(event: Any) -> None:
    """Broadcast an event that has already cleared its transaction."""
    if should_broadcast_now(event):
        _run(_deliver(event))
        return
    _run(_enqueue(event))


async def _deliver(event: Any) -> None:
    from almasix.broadcasting.helpers import get_broadcast_manager

    await get_broadcast_manager().broadcast_event(event)


async def _enqueue(event: Any) -> None:
    """Push the broadcast job, or send it here when there is no queue.

    An application with nothing in `config/queue.py` still broadcasts —
    losing the event because a worker was never configured would be a poor
    trade for a rule nobody asked for.
    """
    from almasix.queue.helpers import dispatch as queue_dispatch

    try:
        await queue_dispatch(job_for(event))
    except KeyError:
        await _deliver(event)


#: Broadcasts started from async code and not yet finished. Holding the tasks
#: keeps them from being garbage collected mid-flight.
_pending: set[asyncio.Task[Any]] = set()


def _run(coroutine: Any) -> None:
    """Run a coroutine from sync code, whether or not a loop is already going.

    Under a running loop the broadcast becomes a task: dispatching an event
    must not block the request that fired it, and — for the websocket driver
    — the send has to happen on the loop that owns the connections.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coroutine)
        return
    task = loop.create_task(coroutine)
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def flush_broadcasts() -> None:
    """Wait for every in-flight broadcast.

    Dispatch hands a broadcast to the loop and returns, which is what you
    want in a request and not what you want in a test or a script that is
    about to exit. Await this and everything fired so far has gone out.
    """
    while _pending:
        await asyncio.gather(*list(_pending), return_exceptions=True)
