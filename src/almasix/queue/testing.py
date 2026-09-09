"""The queue under test — record instead of push, then assert."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from almasix.queue.dispatcher import Dispatcher
from almasix.queue.job import Job


@dataclass
class RecordedJob:
    """One job that would have gone to the queue."""

    job: Job
    connection: str | None
    queue: str
    #: Whether the job would really have been queued, or run in-process.
    queued: bool

    @property
    def name(self) -> str:
        return type(self.job).__name__


class FakeQueue(Dispatcher):
    """A dispatcher that remembers what it was handed.

    Installed by `fake_queue()`. Nothing runs: a faked queue is how a test
    says "the controller's job is to dispatch this, not to do it".
    """

    def __init__(self, jobs: Sequence[type[Job]] | None = None) -> None:
        from almasix.queue.manager import QueueManager

        super().__init__(QueueManager())
        #: When given, only these classes are faked; the rest are dispatched.
        self.only: tuple[type[Job], ...] = tuple(jobs or ())
        self.pushed: list[RecordedJob] = []
        self._real = Dispatcher(self.manager)

    async def dispatch(self, job: Job) -> Any:
        if self.only and not isinstance(job, self.only):
            return await self._real.dispatch(job)
        self.pushed.append(
            RecordedJob(
                job=job,
                connection=job.connection_name(),
                queue=job.queue_name(),
                queued=job.should_queue(),
            )
        )
        return None

    async def dispatch_sync(self, job: Job) -> Any:
        if self.only and not isinstance(job, self.only):
            return await self._real.dispatch_sync(job)
        self.pushed.append(
            RecordedJob(
                job=job, connection=job.connection_name(), queue=job.queue_name(), queued=False
            )
        )
        return None

    # --- assertions -----------------------------------------------------------

    def recorded(
        self,
        job: type[Job] | str | None = None,
        callback: Callable[[Any], bool] | None = None,
    ) -> list[RecordedJob]:
        found = [record for record in self.pushed if _matches(record, job)]
        if callback is None:
            return found
        return [record for record in found if callback(record.job)]

    def assert_pushed(
        self,
        job: type[Job] | str,
        callback: Callable[[Any], bool] | None = None,
    ) -> None:
        if not self.recorded(job):
            raise AssertionError(f"[{_name(job)}] was not pushed. Pushed: {self._pushed_names()}.")
        if callback is not None and not self.recorded(job, callback):
            raise AssertionError(f"[{_name(job)}] was pushed, but not as expected.")

    def assert_not_pushed(self, job: type[Job] | str) -> None:
        if self.recorded(job):
            raise AssertionError(f"[{_name(job)}] was pushed, and should not have been.")

    def assert_pushed_times(self, job: type[Job] | str, times: int = 1) -> None:
        found = len(self.recorded(job))
        if found != times:
            raise AssertionError(f"Expected [{_name(job)}] {times} time(s); it was pushed {found}.")

    def assert_pushed_on(self, queue: str, job: type[Job] | str) -> None:
        if not [record for record in self.recorded(job) if record.queue == queue]:
            queues = ", ".join(sorted({record.queue for record in self.recorded(job)})) or "nothing"
            raise AssertionError(f"[{_name(job)}] was not pushed on [{queue}]. Queues: {queues}.")

    def assert_nothing_pushed(self) -> None:
        if self.pushed:
            raise AssertionError(f"Expected no jobs; got: {self._pushed_names()}.")

    def assert_count(self, count: int) -> None:
        if len(self.pushed) != count:
            raise AssertionError(f"Expected {count} job(s); got {len(self.pushed)}.")

    def flush(self) -> None:
        self.pushed.clear()

    def _pushed_names(self) -> str:
        return ", ".join(record.name for record in self.pushed) or "nothing"

    def __repr__(self) -> str:
        return f"FakeQueue({len(self.pushed)} pushed)"


def fake_queue(jobs: Sequence[type[Job]] | None = None) -> FakeQueue:
    """Swap the dispatcher for one that records (Laravel `Queue::fake()`)."""
    from almasix.queue.helpers import set_dispatcher

    fake = FakeQueue(jobs)
    set_dispatcher(fake)
    return fake


def _name(job: type[Job] | str) -> str:
    return job if isinstance(job, str) else job.__name__


def _matches(record: RecordedJob, job: type[Job] | str | None) -> bool:
    if job is None:
        return True
    if isinstance(job, str):
        return record.name == job
    return isinstance(record.job, job)
