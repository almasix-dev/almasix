"""M31 smoke — the scheduler surface, the page that documents it, and the demo."""

from __future__ import annotations

import pathlib
import re

import pytest

from almasix.console.scheduling import Event, Schedule
from almasix.smith.cli import app as smith_app

pytestmark = pytest.mark.smoke

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROGRESS = ROOT / "examples" / "progress"
PAGE = ROOT / "website" / "src" / "content" / "docs" / "scheduling.md"

# Every frequency, constraint, hook, and mode Laravel's Task Scheduling page
# documents, in its own spelling. The scheduler must answer to all of them.
LARAVEL_METHODS = [
    "cron",
    "everySecond",
    "everyTwoSeconds",
    "everyFiveSeconds",
    "everyTenSeconds",
    "everyFifteenSeconds",
    "everyTwentySeconds",
    "everyThirtySeconds",
    "everyMinute",
    "everyTwoMinutes",
    "everyThreeMinutes",
    "everyFourMinutes",
    "everyFiveMinutes",
    "everyTenMinutes",
    "everyFifteenMinutes",
    "everyThirtyMinutes",
    "hourly",
    "hourlyAt",
    "everyOddHour",
    "everyTwoHours",
    "everyThreeHours",
    "everyFourHours",
    "everySixHours",
    "daily",
    "dailyAt",
    "twiceDaily",
    "twiceDailyAt",
    "daysOfMonth",
    "weekly",
    "weeklyOn",
    "monthly",
    "monthlyOn",
    "twiceMonthly",
    "lastDayOfMonth",
    "quarterly",
    "quarterlyOn",
    "yearly",
    "yearlyOn",
    "timezone",
    "weekdays",
    "weekends",
    "sundays",
    "mondays",
    "tuesdays",
    "wednesdays",
    "thursdays",
    "fridays",
    "saturdays",
    "days",
    "at",
    "between",
    "unlessBetween",
    "when",
    "skip",
    "environments",
    "evenInMaintenanceMode",
    "withoutOverlapping",
    "onOneServer",
    "name",
    "runInBackground",
    "sendOutputTo",
    "appendOutputTo",
    "emailOutputTo",
    "emailOutputOnFailure",
    "before",
    "after",
    "then",
    "onSuccess",
    "onFailure",
    "pingBefore",
    "pingBeforeIf",
    "thenPing",
    "thenPingIf",
    "pingOnSuccess",
    "pingOnSuccessIf",
    "pingOnFailure",
    "pingOnFailureIf",
    "purpose",
]

SCHEDULE_METHODS = ["call", "command", "job", "exec", "group", "useCache"]

# The sections Laravel's page has, in the order it has them.
SECTIONS = [
    "Introduction",
    "Defining schedules",
    "Schedule frequency options",
    "Timezones",
    "Preventing task overlaps",
    "Running tasks on one server",
    "Background tasks",
    "Maintenance mode",
    "Schedule groups",
    "Running the scheduler",
    "Task output",
    "Task hooks",
    "Events",
]

COMMANDS = [
    "schedule:run",
    "schedule:work",
    "schedule:list",
    "schedule:test",
    "schedule:interrupt",
    "schedule:clear-cache",
    "down",
    "up",
]


# --- the surface --------------------------------------------------------------


@pytest.mark.parametrize("method", LARAVEL_METHODS)
def test_every_method_laravels_page_documents_is_on_the_task(method: str) -> None:
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", method).lower()

    assert hasattr(Event, method), f"missing Laravel spelling: {method}"
    assert hasattr(Event, snake), f"missing Python spelling: {snake}"


@pytest.mark.parametrize("method", SCHEDULE_METHODS)
def test_every_way_of_defining_a_task_is_on_the_schedule(method: str) -> None:
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", method).lower()

    assert hasattr(Schedule, snake), f"missing: {snake}"


@pytest.mark.parametrize("command", COMMANDS)
def test_every_scheduler_command_is_registered(command: str) -> None:
    registered = {entry.name for entry in smith_app.registered_commands}

    assert command in registered


# --- the page -----------------------------------------------------------------


@pytest.mark.parametrize("section", SECTIONS)
def test_the_page_keeps_laravels_sections(section: str) -> None:
    assert f"## {section}" in PAGE.read_text(encoding="utf-8")


def test_the_page_documents_every_frequency_and_constraint() -> None:
    page = PAGE.read_text(encoding="utf-8")
    documented = set(re.findall(r"`\.?([a-z_]+)\(", page))

    missing = [
        re.sub(r"(?<!^)(?=[A-Z])", "_", method).lower()
        for method in LARAVEL_METHODS
        if re.sub(r"(?<!^)(?=[A-Z])", "_", method).lower() not in documented
    ]

    assert missing == []


def test_the_page_is_as_thorough_as_the_one_it_ports() -> None:
    # Laravel's Task Scheduling page is 635 lines. The audit found 55 here.
    assert len(PAGE.read_text(encoding="utf-8").splitlines()) > 600


def test_the_page_names_its_deviations_rather_than_hiding_them() -> None:
    page = PAGE.read_text(encoding="utf-8")

    assert "Named deviation" in page
    assert "Not shipped yet" in page


# --- the living example -------------------------------------------------------


@pytest.fixture()
def progress_cwd(monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    from almasix.console.kernel import ConsoleKernel
    from tests.support import purge_generated_app_modules, without_base_path

    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    kernel = ConsoleKernel.from_cwd(PROGRESS)
    kernel.load_console_routes()
    kernel.register_on_typer(smith_app)
    return PROGRESS


def invoke(*argv: str) -> str:
    from typer.testing import CliRunner

    result = CliRunner().invoke(smith_app, list(argv))
    output = result.stdout + (result.stderr or "")
    assert result.exit_code == 0, output
    return output


def test_the_schedule_demo_shows_the_surface_m31_added(progress_cwd: pathlib.Path) -> None:
    del progress_cwd
    output = invoke("progress:schedule")

    assert "0 * * * 1,2,3,4,5" in output  # weekdays and hourly combine
    assert "1-12/3" in output  # quarterly_on
    assert "hooks → ['before', 'task', 'success']" in output
    assert "a constraint turned the task away" in output
    assert "shell-task-output" in output
    assert "schedule demo ok" in output


def test_schedule_list_shows_the_apps_own_schedule(progress_cwd: pathlib.Path) -> None:
    del progress_cwd
    output = invoke("schedule:list")

    assert "progress-heartbeat" in output
    assert "progress:hello" in output
    assert "next:" in output


def test_the_board_marks_the_scheduling_exhaust_complete(progress_cwd: pathlib.Path) -> None:
    del progress_cwd
    from app.http.controllers.progress_controller import _milestones

    entry = next(item for item in _milestones() if item["id"] == "M31")

    assert entry["status"] == "complete"
    assert any("progress:schedule" in proof for proof in entry["proof"])
    assert any("schedule:list" in proof for proof in entry["proof"])
