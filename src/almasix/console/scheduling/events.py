"""The events the scheduler dispatches around each task."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from almasix.console.scheduling.event import Event


@dataclass
class ScheduledTaskStarting:
    """A task is about to run."""

    task: Event


@dataclass
class ScheduledTaskFinished:
    """A task finished, whatever it exited with."""

    task: Event
    runtime: float
    exit_code: int = 0
    output: str = ""


@dataclass
class ScheduledBackgroundTaskFinished:
    """A background task finished, after the tick that started it."""

    task: Event
    exit_code: int = 0
    output: str = ""


@dataclass
class ScheduledTaskSkipped:
    """A task was due but a constraint or a lock turned it away."""

    task: Event
    reason: str = ""


@dataclass
class ScheduledTaskFailed:
    """A task raised, or exited non-zero."""

    task: Event
    exception: BaseException | None = None
    exit_code: int = 1
    output: str = ""


__all__ = [
    "ScheduledBackgroundTaskFinished",
    "ScheduledTaskFailed",
    "ScheduledTaskFinished",
    "ScheduledTaskSkipped",
    "ScheduledTaskStarting",
]
