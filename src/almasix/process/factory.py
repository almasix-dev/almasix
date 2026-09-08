"""Process factory — fakes, recording, and assertions."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from almasix.process.fake import (
    FakeProcessDescription,
    FakeProcessResult,
    FakeProcessSequence,
    normalize_fake,
)
from almasix.process.pending import PendingProcess
from almasix.process.pipe import Pipe, build_pipe
from almasix.process.pool import Pool, ProcessPoolResults
from almasix.process.result import ProcessResult
from almasix.support.arity import accepts_two_arguments


class RecordedProcess:
    """A process the factory saw run, with the result it produced."""

    def __init__(self, process: PendingProcess, result: ProcessResult) -> None:
        self.process = process
        self.result = result

    def update(self, result: ProcessResult) -> None:
        """Replace the placeholder recorded when an async process started."""
        self.result = result

    def __iter__(self) -> Any:
        return iter((self.process, self.result))


class Factory:
    """Creates pending processes and holds fake / recording state."""

    def __init__(self) -> None:
        self._stubs: list[tuple[Callable[[str], bool], Any]] = []
        self._recorded: list[RecordedProcess] = []
        self._faking = False
        self._prevent_stray = False

    # --- building -------------------------------------------------------

    def pending(self) -> PendingProcess:
        return PendingProcess(self)

    def pool(self, callback: Callable[[Pool], Any]) -> Pool:
        pool = Pool(self)
        callback(pool)
        return pool

    def concurrently(self, callback: Callable[[Pool], Any], output: Any = None) -> ProcessPoolResults:
        return self.pool(callback).start(output).wait()

    def pipe(
        self, commands: Callable[[Pipe], Any] | Sequence[Any], output: Any = None
    ) -> ProcessResult:
        return build_pipe(self, commands).run(output)

    # --- faking ---------------------------------------------------------

    def is_faking(self) -> bool:
        return self._faking

    def fake(self, callback: Any = None) -> Factory:
        """Fake every process, a command map, a callable, or a single result."""
        self._faking = True
        if callback is None:
            self._stubs.append((lambda _command: True, FakeProcessResult()))
        elif isinstance(callback, Mapping):
            for pattern, handler in callback.items():
                self._stubs.append((_command_matcher(str(pattern)), handler))
        else:
            self._stubs.append((lambda _command: True, callback))
        return self

    def result(
        self,
        output: str | Sequence[str] = "",
        error_output: str | Sequence[str] = "",
        exit_code: int = 0,
    ) -> FakeProcessResult:
        return FakeProcessResult(output, error_output, exit_code)

    def describe(self) -> FakeProcessDescription:
        return FakeProcessDescription()

    def sequence(self) -> FakeProcessSequence:
        return FakeProcessSequence()

    def fake_sequence(self, command: str | None = None) -> FakeProcessSequence:
        sequence = FakeProcessSequence()
        self._faking = True
        matcher = _command_matcher(command) if command else (lambda _command: True)
        self._stubs.append((matcher, sequence))
        return sequence

    def prevent_stray_processes(self, prevent: bool = True) -> Factory:
        self._prevent_stray = prevent
        return self

    def allow_stray_processes(self) -> Factory:
        self._prevent_stray = False
        return self

    def stray_allowed(self, pending: PendingProcess) -> bool:
        del pending
        return not self._prevent_stray

    def match_fake(self, pending: PendingProcess) -> Any | None:
        """The normalized stub for this process, or ``None`` to run for real."""
        if not self._faking:
            return None
        command = pending.described_command
        for matcher, handler in self._stubs:
            if matcher(command):
                return normalize_fake(handler, pending)
        return None

    # --- recording ------------------------------------------------------

    def record(self, pending: PendingProcess, result: ProcessResult) -> RecordedProcess:
        recorded = RecordedProcess(pending, result)
        self._recorded.append(recorded)
        return recorded

    def recorded(
        self, callback: str | Callable[..., bool] | None = None
    ) -> list[tuple[PendingProcess, ProcessResult]]:
        pairs = [(entry.process, entry.result) for entry in self._recorded]
        if callback is None:
            return pairs
        matcher = _as_process_predicate(callback)
        return [pair for pair in pairs if matcher(*pair)]

    def assert_ran(self, callback: str | Callable[..., bool]) -> None:
        if not self.recorded(callback):
            raise AssertionError("An expected process was not invoked.")

    def assert_didnt_run(self, callback: str | Callable[..., bool]) -> None:
        if self.recorded(callback):
            raise AssertionError("An unexpected process was invoked.")

    def assert_ran_times(self, callback: str | Callable[..., bool], times: int = 1) -> None:
        actual = len(self.recorded(callback))
        if actual != times:
            raise AssertionError(f"Expected the process to run {times} times, it ran {actual}.")

    def assert_nothing_ran(self) -> None:
        if self._recorded:
            raise AssertionError("Processes were invoked when none were expected.")

    def assert_sequences_are_empty(self) -> None:
        for _matcher, handler in self._stubs:
            if isinstance(handler, FakeProcessSequence) and not handler.is_empty():
                raise AssertionError("Not all queued fake processes were consumed.")


def _command_matcher(pattern: str) -> Callable[[str], bool]:
    """Laravel's ``Str::is`` semantics: ``*`` is the only wildcard."""
    expression = ".*".join(re.escape(part) for part in pattern.split("*"))
    compiled = re.compile(f"^{expression}$", re.DOTALL)
    return lambda command: bool(compiled.match(command))


def _as_process_predicate(
    callback: str | Callable[..., bool],
) -> Callable[[PendingProcess, ProcessResult], bool]:
    """Normalize a command pattern or a ``(process[, result])`` callable."""
    if isinstance(callback, str):
        matcher = _command_matcher(callback)
        return lambda process, _result: matcher(process.described_command)
    if accepts_two_arguments(callback):
        return callback
    return lambda process, _result: bool(callback(process))
