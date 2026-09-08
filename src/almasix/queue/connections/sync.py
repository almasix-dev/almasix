"""Sync queue driver — runs jobs immediately in-process."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from almasix.queue.job import Job

if TYPE_CHECKING:
    from almasix.queue.manager import QueueManager


class SyncQueue:
    """Immediate in-process queue (default for tests/dev)."""

    def __init__(
        self,
        app: Any | None,
        config: dict[str, Any],
        *,
        manager: QueueManager | None = None,
    ) -> None:
        self.app = app
        self.config = config
        self.manager = manager

    async def push(self, job: Job) -> Any:
        from almasix.queue.worker import Worker

        worker = Worker(self.manager or _fallback_manager(self.app, self.config))
        return await worker.process_job(job, connection_name="sync")

    async def pop(self, queue: str = "default") -> dict[str, Any] | None:
        return None

    async def size(self, queue: str = "default") -> int:
        return 0


def _fallback_manager(app: Any | None, config: dict[str, Any]) -> Any:
    from almasix.queue.manager import QueueManager

    return QueueManager(app, {"default": "sync", "connections": {"sync": config}})
