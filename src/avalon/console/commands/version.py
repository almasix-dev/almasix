"""``grail version``."""

from __future__ import annotations

from avalon import __version__
from avalon.console.command import Command


class VersionCommand(Command):
    signature = "version"
    description = "Show Avalon version"
    boots_application = False

    def handle(self) -> int:
        self.line(f"Avalon {__version__}")
        return self.SUCCESS
