"""Fork and spawn drivers — real parallelism in child processes."""

from __future__ import annotations

import multiprocessing
import pickle
import traceback
from collections.abc import Sequence
from typing import Any

from almasix.concurrency.drivers.base import Driver, first_failure
from almasix.concurrency.exceptions import TaskFailedException, UnsupportedDriverException
from almasix.concurrency.tasks import Task, TaskSet


class _MultiprocessDriver(Driver):
    """Shared machinery: one child per task, results back over a pipe."""

    #: The ``multiprocessing`` start method this driver uses.
    start_method = ""

    def context(self) -> Any:
        try:
            return multiprocessing.get_context(self.start_method)
        except ValueError as exception:
            raise UnsupportedDriverException(
                f"The {self.name!r} concurrency driver needs the "
                f"{self.start_method!r} start method, which this platform "
                f"does not support."
            ) from exception

    def execute(self, tasks: TaskSet) -> Sequence[Any]:
        context = self.context()
        handles = []
        for task in tasks.tasks:
            receiver, sender = context.Pipe(duplex=False)
            process = context.Process(target=_run_task, args=(sender, task))
            process.start()
            sender.close()
            handles.append((process, receiver))

        outcomes: list[tuple[bool, Any]] = []
        for process, receiver in handles:
            # Read before joining: a result larger than the pipe buffer would
            # block the child, and a child blocked on write never exits.
            outcomes.append(_collect(process, receiver))
        first_failure(outcomes)
        return [value for _ok, value in outcomes]


class ForkDriver(_MultiprocessDriver):
    """Forks a child per task (Laravel's ``fork``).

    The child inherits the parent's memory, so the task itself is never
    pickled and closures work. Only the *result* travels back, so it must be
    picklable. Unix only, and unsafe to mix with threads in the parent.
    """

    name = "fork"
    start_method = "fork"


class ProcessDriver(_MultiprocessDriver):
    """Spawns a fresh interpreter per task (Laravel's ``process``).

    A spawned child inherits nothing, so the task is pickled and must be
    importable — a module-level function, not a lambda. In exchange it works
    on every platform and cannot inherit a broken parent state.
    """

    name = "process"
    start_method = "spawn"

    def execute(self, tasks: TaskSet) -> Sequence[Any]:
        for task in tasks.tasks:
            _require_picklable(task)
        return super().execute(tasks)


def _require_picklable(task: Task) -> None:
    try:
        pickle.dumps(task)
    except (AttributeError, TypeError, pickle.PicklingError) as exception:
        raise UnsupportedDriverException(
            "The 'process' concurrency driver spawns a fresh interpreter, so "
            f"every task must be picklable — {task!r} is not. Use a "
            "module-level function, or the 'fork' or 'thread' driver."
        ) from exception


def _run_task(sender: Any, task: Task) -> None:  # pragma: no cover - child process
    try:
        payload: tuple[bool, Any] = (True, task())
    except BaseException as exception:
        payload = (False, _portable(exception))
    try:
        sender.send(payload)
    except Exception:
        sender.send((False, TaskFailedException(f"{payload[1]!r} could not be returned.")))
    finally:
        sender.close()


def _portable(exception: BaseException) -> BaseException:  # pragma: no cover - child process
    """Return an exception the parent can unpickle, whatever was raised."""
    try:
        pickle.loads(pickle.dumps(exception))
    except Exception:
        return TaskFailedException("".join(traceback.format_exception_only(exception)).strip())
    return exception


def _collect(process: Any, receiver: Any) -> tuple[bool, Any]:
    try:
        ok, value = receiver.recv()
    except EOFError:
        process.join()
        return (
            False,
            TaskFailedException(f"A concurrent task exited with code {process.exitcode}."),
        )
    finally:
        receiver.close()
    process.join()
    return ok, value
