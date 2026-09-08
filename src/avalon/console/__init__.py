"""Console kernel — commands, scheduling, Fiddle REPL, and Prompts (M9/M30)."""

from __future__ import annotations

from avalon.console.command import Command, Isolatable, PromptsForMissingInput
from avalon.console.events import CommandFinished, CommandStarting, ConsoleStarting
from avalon.console.exceptions import CommandFailed, CommandNotFound, ConsoleException
from avalon.console.facade import Artisan
from avalon.console.output import Output
from avalon.console.scheduling import Schedule, schedule

__all__ = [
    "Artisan",
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
