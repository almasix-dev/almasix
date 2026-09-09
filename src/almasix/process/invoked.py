"""A started, still-running process (Laravel ``InvokedProcess``)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from almasix.process.exceptions import ProcessTimedOutException
from almasix.process.result import ProcessResult
from almasix.process.runner import DEFAULT_STOP_TIMEOUT, OutputCallback, ProcessHandle


class InvokedProcess:
    """Handle on a process started with ``Process.start()``."""

    def __init__(
        self,
        handle: ProcessHandle | Any,
        *,
        timeout: float | None = None,
        idle_timeout: float | None = None,
    ) -> None:
        self._handle = handle
        self._timeout = timeout
        self._idle_timeout = idle_timeout
        self._started_at = time.monotonic()
        #: Set by ``PendingProcess.start`` so the recorded result — written
        #: when the process was still running — gains its real exit code.
        self._on_finish: Callable[[ProcessResult], Any] | None = None

    def id(self) -> int:
        """The process ID (Laravel's ``$process->id()``)."""
        return self._handle.pid()

    def running(self) -> bool:
        return self._handle.running()

    def output(self) -> str:
        return self._handle.output()

    def error_output(self) -> str:
        return self._handle.error_output()

    def latest_output(self) -> str:
        return self._handle.latest_output()

    def latest_error_output(self) -> str:
        return self._handle.latest_error_output()

    def signal(self, sig: int) -> InvokedProcess:
        self._handle.signal(sig)
        return self

    def stop(self, timeout: float = DEFAULT_STOP_TIMEOUT, sig: int | None = None) -> int | None:
        return self._handle.stop(timeout, sig)

    def wait(self, callback: OutputCallback | None = None) -> ProcessResult:
        """Block until the process finishes and collect its result."""
        if callback is not None:
            self._handle.set_output_callback(callback)
        exit_code = self._handle.wait(self._timeout, self._idle_timeout)
        if exit_code is None:
            kind = self._handle.timed_out_kind(self._started_at, self._timeout, self._idle_timeout)
            self._handle.stop(1.0)
            raise ProcessTimedOutException(
                _timeout_message(self._handle.command, kind, self._timeout, self._idle_timeout),
                self._finished(self.result(self._handle.exit_code())),
            )
        return self._finished(self.result(exit_code))

    def _finished(self, result: ProcessResult) -> ProcessResult:
        if self._on_finish is not None:
            self._on_finish(result)
        return result

    def result(self, exit_code: int | None = None) -> ProcessResult:
        return ProcessResult(
            self._handle.command,
            self._handle.exit_code() if exit_code is None else exit_code,
            self._handle.output(),
            self._handle.error_output(),
        )


def _timeout_message(
    command: str, kind: str | None, timeout: float | None, idle_timeout: float | None
) -> str:
    if kind == "idle":
        return f'The process "{command}" exceeded the idle timeout of {idle_timeout} seconds.'
    return f'The process "{command}" exceeded the timeout of {timeout} seconds.'
