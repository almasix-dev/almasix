"""``smith version``."""

from __future__ import annotations

from almasix import __version__
from almasix.console.command import Command


class VersionCommand(Command):
    signature = "version"
    description = "Show Almasix version"
    boots_application = False

    def handle(self) -> int:
        self.line(f"Almasix {__version__}")
        return self.SUCCESS
