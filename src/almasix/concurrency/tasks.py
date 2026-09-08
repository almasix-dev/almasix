"""Task collections — Laravel accepts one closure, a list, or a keyed map."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

Task = Callable[[], Any]
Tasks = Task | Sequence[Task] | Mapping[str, Task]
Results = list[Any] | dict[str, Any]


class TaskSet:
    """Normalized tasks that remember the shape their results should take."""

    def __init__(self, keys: list[Any], tasks: list[Task], keyed: bool) -> None:
        self.keys = keys
        self.tasks = tasks
        self.keyed = keyed

    def __len__(self) -> int:
        return len(self.tasks)

    def shape(self, values: Sequence[Any]) -> Results:
        """Return a dict for keyed tasks and a list for everything else."""
        if self.keyed:
            return dict(zip(self.keys, values, strict=True))
        return list(values)


def normalize(tasks: Tasks) -> TaskSet:
    """Accept a single callable, a sequence, or a mapping of callables."""
    if isinstance(tasks, Mapping):
        return TaskSet(list(tasks.keys()), list(tasks.values()), keyed=True)
    if callable(tasks):
        return TaskSet([0], [tasks], keyed=False)
    listed = list(tasks)
    return TaskSet(list(range(len(listed))), listed, keyed=False)
