"""Console events — dispatched through the application event dispatcher."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConsoleStarting:
    """Fired once the console kernel has discovered its commands."""

    commands: list[str] = field(default_factory=list)


@dataclass
class CommandStarting:
    """Fired before a command's ``handle()`` runs."""

    command: str
    arguments: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class CommandFinished:
    """Fired after a command completes, carrying its exit code."""

    command: str
    arguments: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    exit_code: int = 0
