"""Console schedule — loaded by ``python smith schedule:run``."""

from __future__ import annotations

from pathlib import Path

from almasix.console import Smith, schedule


def _greet(name: str, loud: bool, command) -> int:
    """M30 living example — a closure command."""
    message = f"Hello from routes/console.py, {name}"
    command.info(message.upper() if loud else message)
    return 0


Smith.command("progress:greet {name=world} {--loud}", _greet).purpose(
    "M30 living example — closure command"
)


def _heartbeat() -> None:
    stamp = Path("storage/framework/schedule-heartbeat.txt")
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text("ok\n", encoding="utf-8")


schedule.call(_heartbeat, description="progress-heartbeat").every_minute()
schedule.command("progress:hello").hourly()
