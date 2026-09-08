"""``dispatch()`` helper and default queue config."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from almasix.queue.dispatcher import Dispatcher
    from almasix.queue.job import Job
    from almasix.queue.manager import QueueManager

_dispatcher: Dispatcher | None = None
_manager: QueueManager | None = None


def set_dispatcher(dispatcher: Dispatcher | None) -> None:
    global _dispatcher
    _dispatcher = dispatcher


def get_dispatcher() -> Dispatcher:
    if _dispatcher is None:
        from almasix.queue.dispatcher import Dispatcher
        from almasix.queue.manager import QueueManager

        return Dispatcher(QueueManager())
    return _dispatcher


def set_manager(manager: QueueManager | None) -> None:
    global _manager
    _manager = manager


def get_manager() -> QueueManager:
    if _manager is None:
        from almasix.queue.manager import QueueManager

        return QueueManager()
    return _manager


async def dispatch(job: Job) -> Any:
    """Push a job to the queue (or run synchronously when not queueable)."""
    return await get_dispatcher().dispatch(job)


async def dispatch_sync(job: Job) -> Any:
    """Run a job immediately, bypassing queue connections."""
    return await get_dispatcher().dispatch_sync(job)


def default_queue_config(database_connection: str = "default") -> dict[str, Any]:
    """Default ``config/queue.py`` shape."""
    return {
        "default": "sync",
        "connections": {
            "sync": {"driver": "sync"},
            "database": {
                "driver": "database",
                "connection": database_connection,
                "table": "jobs",
                "queue": "default",
                "retry_after": 90,
            },
            "redis": {
                "driver": "redis",
                "connection": "default",
                "queue": "queues",
            },
        },
        "failed": {
            "driver": "database",
            "connection": database_connection,
            "table": "failed_jobs",
        },
    }
