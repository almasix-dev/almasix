"""Driver contract — every driver runs a task set and returns its results."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from almasix.concurrency.tasks import Results, Tasks, TaskSet, normalize


class Driver:
    """Runs tasks concurrently, in whatever way the driver can."""

    #: Name this driver answers to in ``config/concurrency.py``.
    name: ClassVar[str] = ""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = dict(config or {})

    def run(self, tasks: Tasks) -> Results:
        task_set = normalize(tasks)
        if not task_set.tasks:
            return task_set.shape([])
        return task_set.shape(self.execute(task_set))

    def execute(self, tasks: TaskSet) -> Sequence[Any]:  # pragma: no cover - abstract
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r}>"


def first_failure(outcomes: Sequence[tuple[bool, Any]]) -> None:
    """Raise the first task exception, once every task has settled.

    Laravel lets a failing concurrent task throw. Almasix waits for the rest
    first so no task is silently abandoned mid-flight.
    """
    for ok, value in outcomes:
        if not ok:
            raise value
