"""M31 — the schedule commands: run, work, list, test, interrupt, clear-cache."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from avalon.console.scheduling import schedule
from avalon.grail.cli import app as grail_app

runner = CliRunner()

ROUTES = """
from avalon.console import schedule


def heartbeat() -> None:
    print("heartbeat ran")


schedule.call(heartbeat, description="heartbeat").every_minute()
schedule.command("inspire").daily_at("02:00")
"""


@pytest.fixture()
def scheduled_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A minimal app on disk whose routes/console.py defines two tasks."""
    from tests.support import purge_generated_app_modules, without_base_path

    without_base_path(monkeypatch)
    purge_generated_app_modules()
    (tmp_path / "bootstrap").mkdir()
    (tmp_path / "bootstrap" / "app.py").write_text(
        "from pathlib import Path\n"
        "from avalon.framework import Application\n"
        "application = Application.configure(Path(__file__).resolve().parent.parent).create()\n",
        encoding="utf-8",
    )
    (tmp_path / "routes").mkdir()
    (tmp_path / "routes" / "console.py").write_text(ROUTES, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))

    # Each test gets the schedule to itself, and the loader must run again.
    from avalon.console import kernel as kernel_module

    kernel_module._loaded_console_routes.clear()
    schedule.clear()
    yield tmp_path
    schedule.clear()
    kernel_module._loaded_console_routes.clear()


def invoke(*argv: str) -> Any:
    return runner.invoke(grail_app, list(argv))


def write_routes(app_path: Path, body: str) -> None:
    """Redefine the app's scheduled tasks, the way a reader would."""
    from avalon.console import kernel as kernel_module

    (app_path / "routes" / "console.py").write_text(
        "from avalon.console import schedule\n\n" + body,
        encoding="utf-8",
    )
    kernel_module._loaded_console_routes.clear()
    schedule.clear()


def test_schedule_list_shows_every_task_and_its_next_run(scheduled_app: Path) -> None:
    result = invoke("schedule:list")

    assert result.exit_code == 0, result.stdout
    assert "heartbeat" in result.stdout
    assert "inspire" in result.stdout
    assert "next:" in result.stdout


def test_schedule_list_can_report_in_another_timezone(scheduled_app: Path) -> None:
    default = invoke("schedule:list")
    tokyo = invoke("schedule:list", "--timezone", "Asia/Tokyo")

    assert tokyo.exit_code == 0, tokyo.stdout
    assert tokyo.stdout != default.stdout


def test_schedule_list_says_so_when_nothing_is_scheduled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.support import purge_generated_app_modules, without_base_path

    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(tmp_path)
    schedule.clear()

    result = invoke("schedule:list")

    assert "No scheduled tasks are defined." in result.stdout


def test_schedule_run_runs_the_due_task(scheduled_app: Path) -> None:
    result = invoke("schedule:run")

    assert result.exit_code == 0, result.stdout
    assert "Running: heartbeat" in result.stdout
    assert "inspire" not in result.stdout


def test_schedule_run_says_so_when_nothing_is_due(scheduled_app: Path) -> None:
    write_routes(scheduled_app, 'schedule.command("inspire").yearly_on(1, 1, "00:00")\n')

    result = invoke("schedule:run")

    assert "No scheduled tasks are ready." in result.stdout


def test_schedule_run_exits_non_zero_when_a_task_fails(scheduled_app: Path) -> None:
    write_routes(scheduled_app, 'schedule.exec("exit 3").every_minute()\n')

    result = invoke("schedule:run")

    assert result.exit_code == 1
    assert "exit 3" in result.stdout


def test_schedule_run_reports_a_task_a_constraint_turned_away(scheduled_app: Path) -> None:
    write_routes(
        scheduled_app,
        'schedule.call(lambda: None, description="turned-away")'
        ".every_minute().skip(lambda: True)\n",
    )

    result = invoke("schedule:run")

    assert "skipped: turned-away" in result.stdout


def test_schedule_test_runs_the_named_task_whatever_its_frequency(scheduled_app: Path) -> None:
    result = invoke("schedule:test", "--name", "inspire")

    assert result.exit_code == 0, result.stdout
    assert "Running: inspire" in result.stdout


def test_schedule_test_shows_the_output_it_captured(scheduled_app: Path) -> None:
    result = invoke("schedule:test", "--name", "heartbeat")

    assert "heartbeat ran" in result.stdout


def test_schedule_test_refuses_a_name_it_cannot_find(scheduled_app: Path) -> None:
    result = invoke("schedule:test", "--name", "nothing:here")

    assert result.exit_code == 1
    assert "No scheduled task matches" in result.stdout


def test_schedule_test_runs_the_only_task_without_asking(scheduled_app: Path) -> None:
    write_routes(scheduled_app, 'schedule.command("inspire").daily()\n')

    result = invoke("schedule:test")

    assert result.exit_code == 0, result.stdout
    assert "Running: inspire" in result.stdout


def test_schedule_test_asks_which_task_when_there_are_several(
    scheduled_app: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []
    monkeypatch.setattr(
        "avalon.console.prompts.select",
        lambda label, options, **kwargs: asked.append(label) or 1,
    )

    result = invoke("schedule:test")

    assert result.exit_code == 0, result.stdout
    assert asked == ["Which task would you like to run?"]
    assert "Running: inspire" in result.stdout


def test_schedule_test_exits_with_the_task_exit_code(scheduled_app: Path) -> None:
    write_routes(scheduled_app, 'schedule.exec("exit 5").daily()\n')

    result = invoke("schedule:test")

    assert result.exit_code == 5


def test_schedule_test_says_so_when_nothing_is_scheduled(scheduled_app: Path) -> None:
    write_routes(scheduled_app, "")

    result = invoke("schedule:test")

    assert "No scheduled tasks are defined." in result.stdout


def test_schedule_interrupt_signals_the_current_minute(scheduled_app: Path) -> None:
    from datetime import datetime

    from avalon.console.scheduling import interrupted

    result = invoke("schedule:interrupt")

    assert result.exit_code == 0, result.stdout
    assert "Interrupt signalled" in result.stdout
    minute = datetime.now().replace(second=0, microsecond=0)
    assert interrupted(minute, base_path=scheduled_app) is True


def test_schedule_clear_cache_reports_what_it_released(scheduled_app: Path) -> None:
    write_routes(
        scheduled_app, 'schedule.command("stuck").every_minute().without_overlapping()\n'
    )

    from avalon.cache import set_manager
    from avalon.cache.manager import CacheManager

    set_manager(CacheManager(config={"default": "array", "stores": {"array": {"driver": "array"}}}))
    try:
        result = invoke("schedule:clear-cache")
    finally:
        set_manager(None)

    assert "Released lock for: stuck" in result.stdout


def test_schedule_clear_cache_says_so_when_no_locks_are_held(scheduled_app: Path) -> None:
    result = invoke("schedule:clear-cache")

    assert "No scheduled task locks were held." in result.stdout


def test_down_and_up_move_the_application_in_and_out_of_maintenance(
    scheduled_app: Path,
) -> None:
    marker = scheduled_app / "storage" / "framework" / "down"

    assert invoke("down").exit_code == 0
    assert marker.is_file()
    # The scheduler stops while the marker is there.
    assert "skipped: heartbeat" in invoke("schedule:run").stdout

    assert invoke("up").exit_code == 0
    assert not marker.exists()
    assert "skipped" not in invoke("schedule:run").stdout


def test_schedule_work_ticks_until_it_is_interrupted(
    scheduled_app: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticks: list[int] = []

    def sleep(seconds: float) -> None:
        ticks.append(1)
        raise KeyboardInterrupt

    monkeypatch.setattr("time.sleep", sleep)

    result = invoke("schedule:work", "--sleep", "1")

    assert result.exit_code == 0, result.stdout
    assert "Schedule worker started" in result.stdout
    assert "Schedule worker stopped." in result.stdout
    assert ticks == [1]
