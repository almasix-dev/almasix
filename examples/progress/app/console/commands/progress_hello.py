"""Progress demo console command."""

from __future__ import annotations

from almasix.console import Command


class ProgressHelloCommand(Command):
    signature = "progress:hello {name?}"
    description = "M9 living example — greet from the console"

    def handle(self) -> int:
        name = self.argument("name") or "Almasix"
        self.success(f"Hello, {name} — console kernel is alive.")
        return 0
