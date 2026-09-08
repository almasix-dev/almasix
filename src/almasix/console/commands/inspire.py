"""Framework console commands — inspire."""

from __future__ import annotations

import random

from almasix.console.command import Command


class InspireCommand(Command):
    signature = "inspire"
    description = "Display an inspiring quote"

    def handle(self) -> int:
        quotes = [
            "The only way to do great work is to love what you do. — Steve Jobs",
            "Simplicity is the ultimate sophistication. — Leonardo da Vinci",
            "Code is poetry — when the framework stays out of the way.",
            "First make it work, then make it right, then make it fast.",
        ]
        self.line(random.choice(quotes))
        return 0
