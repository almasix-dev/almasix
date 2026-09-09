"""Framework console commands — inspire."""

from __future__ import annotations

import random

from almasix.console.command import Command

_QUOTES: tuple[tuple[str, str], ...] = (
    ("The only way to do great work is to love what you do.", "Steve Jobs"),
    ("Simplicity is the ultimate sophistication.", "Leonardo da Vinci"),
    ("Code is poetry — when the framework stays out of the way.", ""),
    ("First make it work, then make it right, then make it fast.", ""),
)


class InspireCommand(Command):
    signature = "inspire"
    description = "Display an inspiring quote"

    def handle(self) -> int:
        body, attribution = random.choice(_QUOTES)
        self.output.quote(body, attribution)
        return 0
