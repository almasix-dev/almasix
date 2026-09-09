"""Console kernel — commands, scheduling, Loupe REPL, and Prompts (M9/M30)."""

from __future__ import annotations

from almasix.console.command import Command, Isolatable, PromptsForMissingInput
from almasix.console.events import CommandFinished, CommandStarting, ConsoleStarting
from almasix.console.exceptions import CommandFailed, CommandNotFound, ConsoleException
from almasix.console.facade import Smith
from almasix.console.output import Output
from almasix.console.scheduling import Schedule, schedule

__all__ = [
    "Smith",
    "Command",
    "CommandFailed",
    "CommandFinished",
    "CommandNotFound",
    "CommandStarting",
    "ConsoleException",
    "ConsoleStarting",
    "Isolatable",
    "Output",
    "PromptsForMissingInput",
    "Schedule",
    "schedule",
]
