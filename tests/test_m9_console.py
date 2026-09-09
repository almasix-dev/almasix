"""M9 unit tests — Command, schedule, mutex, kernel."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from almasix.console.command import Command, parse_signature
from almasix.console.kernel import ConsoleKernel
from almasix.console.mutex import Mutex
from almasix.console.scheduling import Event, _cron_matches, run_event, schedule
from almasix.smith.cli import app as smith_app
from tests.support import purge_generated_app_modules

runner = CliRunner()


class DemoCommand(Command):
    signature = "demo:hello {name?} {--yell}"
    description = "Demo"

    def handle(self) -> int:
        name = self.argument("name") or "world"
        message = f"Hello, {name}"
        if self.option("yell"):
            message = message.upper()
        self.line(message)
        return 0


def test_parse_signature() -> None:
    name, args, opts = parse_signature("mail:send {user} {--queue=default}")
    assert name == "mail:send"
    assert args[0]["name"] == "user"
    assert opts[0]["name"] == "queue"
    assert opts[0]["default"] == "default"


def test_command_run_arguments() -> None:
    cmd = DemoCommand()
    assert cmd.run(arguments={"name": "Almasix"}, options={"yell": True}) == 0


def test_cron_matching() -> None:
    moment = datetime(2026, 9, 5, 10, 0, 0)  # Saturday
    assert _cron_matches("0 * * * *", moment)
    assert not _cron_matches("5 * * * *", moment)
    assert _cron_matches("*/5 * * * *", moment)
    event = Event("x").hourly().weekends()
    assert event.is_due(moment)


def test_mutex_exclusive(tmp_path: Path) -> None:
    first = Mutex(tmp_path, "job")
    second = Mutex(tmp_path, "job")
    assert first.acquire() is True
    assert second.acquire() is False
    first.release()
    assert second.acquire() is True
    second.release()


def test_schedule_run_event_callback(tmp_path: Path) -> None:
    seen: list[str] = []
    event = Event("cb", callback=lambda: seen.append("ok")).every_minute()
    event.without_overlapping_lock()
    assert run_event(event, base_path=tmp_path) == 0
    assert seen == ["ok"]


def test_console_kernel_discovers_inspire(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    purge_generated_app_modules()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        'config = {"name": "Console", "debug": False, "providers": []}\n',
        encoding="utf-8",
    )
    (tmp_path / "config" / "logging.py").write_text(
        "config = {'default': 'null', 'channels': {'null': {'driver': 'null'}}}\n",
        encoding="utf-8",
    )
    (tmp_path / "routes").mkdir()
    (tmp_path / "bootstrap").mkdir()
    (tmp_path / "bootstrap" / "app.py").write_text("# stub\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    kernel = ConsoleKernel.from_cwd(tmp_path)
    assert "inspire" in kernel.commands
    assert kernel.run_command("inspire") == 0


def test_smith_make_command_and_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    purge_generated_app_modules()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bootstrap").mkdir()
    (tmp_path / "bootstrap" / "app.py").write_text("asgi = None\n", encoding="utf-8")
    result = runner.invoke(smith_app, ["make:command", "SendDigest"])
    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "app" / "console" / "commands" / "send_digest.py").is_file()
    listed = runner.invoke(smith_app, ["list"])
    assert listed.exit_code == 0
    assert "make:command" in listed.stdout


def test_schedule_singleton_command_event() -> None:
    schedule.events.clear()
    schedule.command("inspire").every_minute()
    assert schedule.due_events(datetime.now())
    schedule.events.clear()
