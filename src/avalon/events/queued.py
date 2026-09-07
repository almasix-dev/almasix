"""Queued event listeners — push work onto Avalon's queue."""

from __future__ import annotations

import asyncio
import importlib
import inspect
from typing import Any

from avalon.queue.job import Job, ShouldQueue


def is_should_queue(obj: Any) -> bool:
    if inspect.isclass(obj):
        try:
            return issubclass(obj, ShouldQueue)
        except TypeError:  # pragma: no cover - exotic typing objects
            return False
    return isinstance(obj, ShouldQueue)


class CallQueuedListener(Job, ShouldQueue):
    """Job that invokes a listener method for a stored event payload."""

    def __init__(
        self,
        listener_path: str,
        method: str = "handle",
        event: Any = None,
        *,
        connection: str | None = None,
        queue: str | bool = "default",
        delay: float = 0,
    ) -> None:
        self.listener_path = listener_path
        self.method = method
        self.event = event
        if connection is not None:
            self.connection = connection
        self.queue = queue
        if delay:
            self.delay = delay

    def handle(self) -> Any:
        listener_cls = _import_symbol(self.listener_path)
        listener = listener_cls()
        return getattr(listener, self.method)(self.event)


def queue_listener(listener: Any, event: Any, *, method: str = "handle") -> None:
    """Push :class:`CallQueuedListener` for a class-based listener."""
    listener_cls = listener if inspect.isclass(listener) else type(listener)
    path = f"{listener_cls.__module__}.{listener_cls.__qualname__}"
    connection = getattr(listener, "connection", None)
    queue = getattr(listener, "queue", "default")
    delay = getattr(listener, "delay", 0)
    if not inspect.isclass(listener):
        if hasattr(listener, "via_connection"):
            connection = listener.via_connection()
        if hasattr(listener, "via_queue"):
            queue = listener.via_queue()
        if hasattr(listener, "with_delay"):
            delay = listener.with_delay(event)

    job = CallQueuedListener(
        path,
        method,
        event,
        connection=connection,
        queue=queue,
        delay=delay,
    )
    _run_dispatch(job)


def _run_dispatch(job: Job) -> None:
    from avalon.queue.helpers import dispatch as queue_dispatch

    async def _go() -> None:
        await queue_dispatch(job)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_go())
        return
    loop.create_task(_go())  # pragma: no cover - requires running event loop


def _import_symbol(path: str) -> Any:
    module_path, _, name = path.rpartition(".")
    if not module_path:
        raise ImportError(f"Invalid path: {path}")
    return getattr(importlib.import_module(module_path), name)
