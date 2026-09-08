"""Console exceptions."""

from __future__ import annotations


class ConsoleException(Exception):
    """Base console error."""


class CommandFailed(ConsoleException):
    """Raised by ``Command.fail()`` to abort with a failure exit code."""


class CommandNotFound(ConsoleException, KeyError):
    """No command is registered under the given name.

    Also a ``KeyError`` so callers written against the original kernel keep
    working.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Command not found: {name}")

    def __str__(self) -> str:
        return f"Command not found: {self.name}"
