"""Maintenance mode — ``down`` and ``up``.

Both commands only move one marker file. Everything that cares reads it:
the scheduler skips its tasks while it is there, and the HTTP kernel answers
503 (Laravel's ``storage/framework/down``).
"""

from __future__ import annotations

from pathlib import Path

from avalon.console.command import Command


def _marker(base_path: Path) -> Path:
    return base_path / "storage" / "framework" / "down"


class DownCommand(Command):
    signature = "down"
    description = "Put the application into maintenance mode (scheduled tasks stop)"

    def handle(self) -> int:
        path = _marker(self.app.base_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("down", encoding="utf-8")
        self.line("Application is now in maintenance mode.")
        return self.SUCCESS


class UpCommand(Command):
    signature = "up"
    description = "Bring the application out of maintenance mode"

    def handle(self) -> int:
        _marker(self.app.base_path).unlink(missing_ok=True)
        self.line("Application is now live.")
        return self.SUCCESS
