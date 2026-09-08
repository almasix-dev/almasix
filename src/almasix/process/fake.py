"""Fake processes — results, descriptions, sequences, and their handles."""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from typing import Any

from almasix.process.exceptions import ProcessException
from almasix.process.result import ProcessResult
from almasix.process.runner import ERR, OUT, OutputCallback

_fake_pids = itertools.count(1000)


def _as_text(output: str | Sequence[str]) -> str:
    """Accept a string or a list of lines, the way Laravel's fakes do."""
    if isinstance(output, str):
        return output if output.endswith("\n") or output == "" else output + "\n"
    return "".join(line if line.endswith("\n") else line + "\n" for line in output)


class OutOfFakeProcesses(ProcessException):
    """A fake process sequence ran out of queued results."""


class FakeProcessHandle:
    """Stands in for :class:`~almasix.process.runner.ProcessHandle`.

    Output arrives in steps: every ``running()`` check releases the next
    chunk, which is how Laravel lets a test walk an asynchronous process
    through its lifecycle without a real subprocess.
    """

    def __init__(
        self,
        command: str,
        steps: Sequence[tuple[str, str]],
        exit_code: int,
        *,
        pid: int | None = None,
        output_callback: OutputCallback | None = None,
    ) -> None:
        self.command = command
        self._steps = list(steps)
        self._exit_code = exit_code
        self._pid = pid if pid is not None else next(_fake_pids)
        self._output: list[str] = []
        self._error_output: list[str] = []
        self._seen_output = 0
        self._seen_error_output = 0
        self._finished = False
        self._output_callback = output_callback
        self.signals: list[int] = []
        self.stopped = False

    # --- lifecycle ------------------------------------------------------

    def pid(self) -> int:
        return self._pid

    def running(self) -> bool:
        if self._finished:
            return False
        if self._steps:
            self._release(self._steps.pop(0))
            return True
        self._finished = True
        return False

    def exit_code(self) -> int | None:
        return self._exit_code if self._finished else None

    def signal(self, sig: int) -> None:
        self.signals.append(sig)

    def stop(self, timeout: float = 10.0, sig: int | None = None) -> int | None:
        del timeout
        self.stopped = True
        if sig is not None:
            self.signals.append(sig)
        return self.wait_for_exit()

    def wait_for_exit(self) -> int | None:
        self._drain()
        return self._exit_code

    def wait(self, timeout: float | None = None, idle_timeout: float | None = None) -> int | None:
        del timeout, idle_timeout
        return self.wait_for_exit()

    def timed_out_kind(
        self, started_at: float, timeout: float | None, idle_timeout: float | None
    ) -> str | None:
        del started_at, timeout, idle_timeout
        return None

    # --- output ---------------------------------------------------------

    def output(self) -> str:
        return "".join(self._output)

    def error_output(self) -> str:
        return "".join(self._error_output)

    def latest_output(self) -> str:
        chunk = "".join(self._output[self._seen_output :])
        self._seen_output = len(self._output)
        return chunk

    def latest_error_output(self) -> str:
        chunk = "".join(self._error_output[self._seen_error_output :])
        self._seen_error_output = len(self._error_output)
        return chunk

    def set_output_callback(self, callback: OutputCallback | None) -> None:
        self._output_callback = callback

    # --- internals ------------------------------------------------------

    def _drain(self) -> None:
        while self._steps:
            self._release(self._steps.pop(0))
        self._finished = True

    def _release(self, step: tuple[str, str]) -> None:
        kind, text = step
        sink = self._output if kind == OUT else self._error_output
        sink.append(text)
        if self._output_callback is not None:
            self._output_callback(kind, text)


class FakeProcessResult:
    """A canned result (Laravel ``Process::result()``)."""

    def __init__(
        self,
        output: str | Sequence[str] = "",
        error_output: str | Sequence[str] = "",
        exit_code: int = 0,
    ) -> None:
        self._output = _as_text(output)
        self._error_output = _as_text(error_output)
        self._exit_code = exit_code

    def as_result(self, command: str) -> ProcessResult:
        return ProcessResult(command, self._exit_code, self._output, self._error_output)

    def as_handle(self, command: str) -> FakeProcessHandle:
        steps: list[tuple[str, str]] = []
        if self._output:
            steps.append((OUT, self._output))
        if self._error_output:
            steps.append((ERR, self._error_output))
        return FakeProcessHandle(command, steps, self._exit_code)


class FakeProcessDescription:
    """A scripted asynchronous process (Laravel ``Process::describe()``)."""

    def __init__(self) -> None:
        self._steps: list[tuple[str, str]] = []
        self._exit_code = 0
        self._pid: int | None = None
        self._run_iterations = 0

    def id(self, process_id: int) -> FakeProcessDescription:
        self._pid = process_id
        return self

    def output(self, output: str | Sequence[str]) -> FakeProcessDescription:
        self._steps.append((OUT, _as_text(output)))
        return self

    def error_output(self, output: str | Sequence[str]) -> FakeProcessDescription:
        self._steps.append((ERR, _as_text(output)))
        return self

    def replace_output(self, output: str | Sequence[str]) -> FakeProcessDescription:
        self._steps = [step for step in self._steps if step[0] != OUT]
        return self.output(output)

    def replace_error_output(self, output: str | Sequence[str]) -> FakeProcessDescription:
        self._steps = [step for step in self._steps if step[0] != ERR]
        return self.error_output(output)

    def exit_code(self, exit_code: int) -> FakeProcessDescription:
        self._exit_code = exit_code
        return self

    def iterations(self, iterations: int) -> FakeProcessDescription:
        """Keep ``running()`` true for this many extra checks."""
        self._run_iterations = iterations
        return self

    def runs_for(self, iterations: int) -> FakeProcessDescription:
        return self.iterations(iterations)

    def _all_steps(self) -> list[tuple[str, str]]:
        # Padding steps emit nothing but keep the process "running", which is
        # how ``runs_for(3)`` makes three ``running()`` checks return true.
        padding = max(self._run_iterations - len(self._steps), 0)
        return [*self._steps, *[(OUT, "")] * padding]

    def as_result(self, command: str) -> ProcessResult:
        output = "".join(text for kind, text in self._all_steps() if kind == OUT)
        error_output = "".join(text for kind, text in self._all_steps() if kind == ERR)
        return ProcessResult(command, self._exit_code, output, error_output)

    def as_handle(self, command: str) -> FakeProcessHandle:
        return FakeProcessHandle(command, self._all_steps(), self._exit_code, pid=self._pid)


class FakeProcessSequence:
    """Queued fake processes (Laravel ``Process::sequence()``)."""

    def __init__(self) -> None:
        self._queue: list[Any] = []
        self._empty: Any = None
        self._fail_when_empty = True

    def push(self, handler: Any) -> FakeProcessSequence:
        self._queue.append(handler)
        return self

    def push_result(
        self,
        output: str | Sequence[str] = "",
        error_output: str | Sequence[str] = "",
        exit_code: int = 0,
    ) -> FakeProcessSequence:
        return self.push(FakeProcessResult(output, error_output, exit_code))

    def push_output(self, output: str | Sequence[str]) -> FakeProcessSequence:
        return self.push_result(output)

    def push_error_output(self, output: str | Sequence[str]) -> FakeProcessSequence:
        return self.push_result("", output, 1)

    def when_empty(self, handler: Any) -> FakeProcessSequence:
        self._empty = handler
        self._fail_when_empty = False
        return self

    def dont_fail_when_empty(self) -> FakeProcessSequence:
        self._fail_when_empty = False
        if self._empty is None:
            self._empty = FakeProcessResult()
        return self

    def fail_when_empty(self) -> FakeProcessSequence:
        self._fail_when_empty = True
        return self

    def is_empty(self) -> bool:
        return not self._queue

    def next(self, command: str) -> Any:
        if self._queue:
            return self._queue.pop(0)
        if self._fail_when_empty:
            raise OutOfFakeProcesses(f"No more fake processes for [{command}].")
        return self._empty


def normalize_fake(handler: Any, pending: Any) -> Any:
    """Resolve a stub into something with ``as_result`` / ``as_handle``.

    Strings and lists of lines become successful output, callables are
    invoked with the pending process, and sequences pop their next entry.
    """
    command = pending.described_command
    seen: set[int] = set()
    while True:
        if isinstance(handler, FakeProcessSequence):
            handler = handler.next(command)
            continue
        if isinstance(handler, ProcessResult):
            handler = FakeProcessResult(
                handler.output(), handler.error_output(), handler.exit_code() or 0
            )
            continue
        if isinstance(handler, (FakeProcessResult, FakeProcessDescription)):
            return handler
        if handler is None:
            return FakeProcessResult()
        if isinstance(handler, (str, list, tuple)):
            return FakeProcessResult(handler)
        if callable(handler):
            if id(handler) in seen:  # pragma: no cover - defensive against loops
                raise ProcessException("A fake process callback returned itself.")
            seen.add(id(handler))
            handler = handler(pending)
            continue
        raise ProcessException(f"Unsupported fake process stub: {handler!r}")
