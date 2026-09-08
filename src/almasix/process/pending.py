"""Fluent pending process (Laravel ``PendingProcess``)."""

from __future__ import annotations

import copy
import os
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from almasix.process.exceptions import (
    ProcessNotStartedException,
    ProcessTimedOutException,
    StrayProcessException,
)
from almasix.process.invoked import InvokedProcess, _timeout_message
from almasix.process.result import ProcessResult
from almasix.process.runner import OutputCallback, ProcessHandle, describe_command

#: Laravel's default process timeout, in seconds.
DEFAULT_TIMEOUT = 60.0


class PendingProcess:
    """Builder that runs or starts one process.

    Fluent calls return a copy, so a configured builder can be reused:
    ``git = Process.path(repo).timeout(5)`` then ``git.run("git status")``.
    """

    def __init__(self, factory: Any = None) -> None:
        self._factory = factory
        self._command: str | Sequence[str] | None = None
        self._path: str | os.PathLike[str] | None = None
        self._timeout: float | None = DEFAULT_TIMEOUT
        self._idle_timeout: float | None = None
        self._env: dict[str, str] = {}
        self._input: str | bytes | None = None
        self._quietly = False
        self._tty = False
        self._options: dict[str, Any] = {}
        #: Set by ``Pool.as_()`` so pool results can be keyed by name.
        self._key: str | int | None = None

    def _clone(self) -> PendingProcess:
        cloned = copy.copy(self)
        cloned._env = dict(self._env)
        cloned._options = dict(self._options)
        return cloned

    # --- configuration --------------------------------------------------

    def command(self, command: str | Sequence[str]) -> PendingProcess:
        cloned = self._clone()
        cloned._command = command
        return cloned

    def path(self, directory: str | os.PathLike[str]) -> PendingProcess:
        cloned = self._clone()
        cloned._path = directory
        return cloned

    def timeout(self, seconds: float) -> PendingProcess:
        cloned = self._clone()
        cloned._timeout = seconds
        return cloned

    def idle_timeout(self, seconds: float) -> PendingProcess:
        cloned = self._clone()
        cloned._idle_timeout = seconds
        return cloned

    def forever(self) -> PendingProcess:
        """Let the process run without a timeout."""
        cloned = self._clone()
        cloned._timeout = None
        return cloned

    def env(self, environment: Mapping[str, Any]) -> PendingProcess:
        cloned = self._clone()
        cloned._env.update({str(k): str(v) for k, v in environment.items()})
        return cloned

    def input(self, input: str | bytes) -> PendingProcess:
        cloned = self._clone()
        cloned._input = input
        return cloned

    def quietly(self) -> PendingProcess:
        """Discard output rather than streaming it to the parent terminal."""
        cloned = self._clone()
        cloned._quietly = True
        return cloned

    def tty(self, tty: bool = True) -> PendingProcess:
        """Run attached to the parent terminal (output is not captured)."""
        cloned = self._clone()
        cloned._tty = tty
        return cloned

    def options(self, options: Mapping[str, Any]) -> PendingProcess:
        """Extra keyword arguments handed to :class:`subprocess.Popen`."""
        cloned = self._clone()
        cloned._options.update(dict(options))
        return cloned

    def when(
        self, condition: Any, callback: Callable[..., Any], default: Callable[..., Any] | None = None
    ) -> PendingProcess:
        if callable(condition):
            condition = condition(self)
        if condition:
            return callback(self, condition) or self
        if default is not None:
            return default(self, condition) or self
        return self

    def unless(
        self, condition: Any, callback: Callable[..., Any], default: Callable[..., Any] | None = None
    ) -> PendingProcess:
        if callable(condition):
            condition = condition(self)
        return self.when(not condition, callback, default)

    # --- inspection -----------------------------------------------------

    @property
    def described_command(self) -> str:
        """The command as a single string, the way fakes match on it."""
        if self._command is None:
            return ""
        return describe_command(self._command)

    def command_line(self) -> str:
        return self.described_command

    def working_directory(self) -> str | os.PathLike[str] | None:
        return self._path

    def environment(self) -> dict[str, str]:
        return dict(self._env)

    def timeout_seconds(self) -> float | None:
        return self._timeout

    def idle_timeout_seconds(self) -> float | None:
        return self._idle_timeout

    def is_quiet(self) -> bool:
        return self._quietly

    def uses_tty(self) -> bool:
        return self._tty

    def input_content(self) -> str | bytes | None:
        return self._input

    # --- execution ------------------------------------------------------

    def run(
        self,
        command: str | Sequence[str] | None = None,
        output_callback: OutputCallback | None = None,
    ) -> ProcessResult:
        """Run the process and block until it finishes."""
        pending = self if command is None else self.command(command)
        pending._require_command()

        fake = pending._fake_handler()
        if fake is not None:
            result = fake.as_result(pending.described_command)
            pending._record(result)
            return result

        handle = pending._spawn(output_callback)
        started_at = time.monotonic()
        exit_code = handle.wait(pending._timeout, pending._idle_timeout)
        if exit_code is None:
            kind = handle.timed_out_kind(started_at, pending._timeout, pending._idle_timeout)
            handle.stop(1.0)
            result = pending._result_from(handle)
            pending._record(result)
            raise ProcessTimedOutException(
                _timeout_message(
                    pending.described_command, kind, pending._timeout, pending._idle_timeout
                ),
                result,
            )
        result = pending._result_from(handle, exit_code)
        pending._record(result)
        return result

    def start(
        self,
        command: str | Sequence[str] | None = None,
        output_callback: OutputCallback | None = None,
    ) -> InvokedProcess:
        """Start the process and return immediately."""
        pending = self if command is None else self.command(command)
        pending._require_command()

        fake = pending._fake_handler()
        if fake is not None:
            handle = fake.as_handle(pending.described_command)
        else:
            handle = pending._spawn(output_callback)

        invoked = InvokedProcess(
            handle, timeout=pending._timeout, idle_timeout=pending._idle_timeout
        )
        record = pending._record(invoked.result())
        if record is not None:
            invoked._on_finish = record.update  # type: ignore[attr-defined]
        return invoked

    # --- internals ------------------------------------------------------

    def _require_command(self) -> None:
        if not self.described_command:
            raise ProcessNotStartedException("No command has been given to the process.")

    def _spawn(self, output_callback: OutputCallback | None) -> ProcessHandle:
        assert self._command is not None
        return ProcessHandle(
            self._command,
            cwd=self._path,
            env=self._env or None,
            input=self._input,
            tty=self._tty,
            quietly=self._quietly,
            options=self._options,
            output_callback=output_callback,
        )

    def _result_from(self, handle: ProcessHandle, exit_code: int | None = None) -> ProcessResult:
        return ProcessResult(
            self.described_command,
            handle.exit_code() if exit_code is None else exit_code,
            handle.output(),
            handle.error_output(),
        )

    def _fake_handler(self) -> Any | None:
        factory = self._factory
        if factory is None or not factory.is_faking():
            return None
        handler = factory.match_fake(self)
        if handler is None:
            if not factory.stray_allowed(self):
                raise StrayProcessException(self.described_command)
            return None
        return handler

    def _record(self, result: ProcessResult) -> Any | None:
        if self._factory is None:
            return None
        return self._factory.record(self, result)
