"""Thread driver — concurrency for I/O-bound work, and any callable."""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from almasix.concurrency.drivers.base import Driver, first_failure
from almasix.concurrency.tasks import TaskSet

DEFAULT_MAX_WORKERS = 16


class ThreadDriver(Driver):
    """Runs every task on a thread pool.

    This is Almasix's default because it is the only driver that accepts any
    callable — closures included — and because the work Laravel's Concurrency
    page reaches for (queries, HTTP calls) releases the GIL anyway.
    """

    name = "thread"

    def execute(self, tasks: TaskSet) -> Sequence[Any]:
        limit = int(self.config.get("max_workers") or DEFAULT_MAX_WORKERS)
        workers = min(limit, len(tasks))
        outcomes: list[tuple[bool, Any]] = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(task) for task in tasks.tasks]
            for future in futures:
                try:
                    outcomes.append((True, future.result()))
                except Exception as exception:  # noqa: BLE001 - reported below
                    outcomes.append((False, exception))
        first_failure(outcomes)
        return [value for _ok, value in outcomes]
