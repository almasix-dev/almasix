"""Job dispatcher — resolve connection and push or run synchronously."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from almasix.queue.job import Job, call_handle, run_through_middleware

if TYPE_CHECKING:
    from almasix.queue.manager import QueueManager


class Dispatcher:
    """Dispatches jobs to queue connections or runs them in-process."""

    def __init__(self, manager: QueueManager) -> None:
        self.manager = manager

    async def dispatch(self, job: Job) -> Any:
        if job.should_queue():
            connection_name = self._resolve_connection(job)
            connection = self.manager.connection(connection_name)
            return await connection.push(job)
        return await self.dispatch_sync(job)

    async def dispatch_sync(self, job: Job) -> Any:
        return await run_through_middleware(job, self._execute)

    async def _execute(self, job: Job) -> Any:
        return await call_handle(job)

    def _resolve_connection(self, job: Job) -> str:
        explicit = job.connection_name()
        if explicit:
            return explicit
        return self.manager.get_default_connection()
