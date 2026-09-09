"""Finished process result (Laravel ``ProcessResult``)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from almasix.process.exceptions import ProcessFailedException


class ProcessResult:
    """The outcome of a finished process."""

    def __init__(
        self,
        command: str,
        exit_code: int | None,
        output: str = "",
        error_output: str = "",
    ) -> None:
        self._command = command
        self._exit_code = exit_code
        self._output = output
        self._error_output = error_output

    def command(self) -> str:
        return self._command

    def successful(self) -> bool:
        return self._exit_code == 0

    def failed(self) -> bool:
        return not self.successful()

    def exit_code(self) -> int | None:
        return self._exit_code

    def output(self) -> str:
        return self._output

    def error_output(self) -> str:
        return self._error_output

    def see_in_output(self, output: str) -> bool:
        return output in self._output

    def see_in_error_output(self, output: str) -> bool:
        return output in self._error_output

    def throw(self, callback: Callable[..., Any] | None = None) -> ProcessResult:
        """Raise :class:`ProcessFailedException` when the process failed."""
        if self.successful():
            return self
        exception = ProcessFailedException(self)
        if callback is not None:
            callback(self, exception)
        raise exception

    def throw_if(self, condition: Any, callback: Callable[..., Any] | None = None) -> ProcessResult:
        if callable(condition):
            condition = condition(self)
        if condition:
            return self.throw(callback)
        return self

    def throw_unless(
        self, condition: Any, callback: Callable[..., Any] | None = None
    ) -> ProcessResult:
        if callable(condition):
            condition = condition(self)
        return self.throw_if(not condition, callback)

    def __repr__(self) -> str:
        return f"<ProcessResult command={self._command!r} exit_code={self._exit_code!r}>"
