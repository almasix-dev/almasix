"""Sync driver — runs tasks in order in the current process."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from almasix.concurrency.drivers.base import Driver
from almasix.concurrency.tasks import TaskSet


class SyncDriver(Driver):
    """No concurrency at all, for local debugging (Laravel's ``sync``)."""

    name = "sync"

    def execute(self, tasks: TaskSet) -> Sequence[Any]:
        return [task() for task in tasks.tasks]
