"""Process exceptions (Laravel-shaped)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from almasix.process.result import ProcessResult


class ProcessException(Exception):
    """Base process error."""


class ProcessFailedException(ProcessException):
    """A process exited with a non-zero status and ``throw()`` was called.

    The message carries the exit code plus the output and error output, as
    Laravel's does. The result itself hangs off :attr:`result`, and unknown
    attributes proxy to it so ``exception.exit_code()`` works.
    """

    def __init__(self, result: ProcessResult) -> None:
        self.result = result
        super().__init__(_message_for(result))

    def __getattr__(self, name: str) -> Any:
        return getattr(self.result, name)


class ProcessTimedOutException(ProcessException):
    """A process exceeded its timeout or idle timeout.

    Carries the partial :attr:`result` collected before the process was
    killed, so callers can still read whatever output arrived.
    """

    def __init__(self, message: str, result: ProcessResult | None = None) -> None:
        self.result = result
        super().__init__(message)


class StrayProcessException(ProcessException):
    """A process was started that has no matching fake."""

    def __init__(self, command: str) -> None:
        self.command = command
        super().__init__(f"Attempted process [{command}] without a matching fake.")


class ProcessNotStartedException(ProcessException):
    """A pending process was run without a command."""


def _message_for(result: ProcessResult) -> str:
    message = f"The command \"{result.command()}\" failed.\n\nExit Code: {result.exit_code()}"
    output = result.output().strip()
    error_output = result.error_output().strip()
    if output:
        message = f"{message}\n\nOutput:\n{output}"
    if error_output:
        message = f"{message}\n\nError Output:\n{error_output}"
    return message
