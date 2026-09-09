"""The ``schedule:*`` commands — run, work, list, test, interrupt, clear-cache.

Cron calls ``schedule:run`` every minute; everything else here is for the
person at the keyboard, asking what is scheduled, running one task now, or
clearing up after a stuck one.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from rich.style import Style
from rich.text import Text

from almasix.console.command import Command
from almasix.console.output import Output
from almasix.console.prompts.style import (
    CHECK,
    CROSS,
    OD_COMMENT,
    OD_CYAN,
    OD_FG,
    OD_GREEN,
    OD_RED,
    OD_YELLOW,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from almasix.console.scheduling.event import Event
    from almasix.console.scheduling.runner import Outcome, Runner
    from almasix.console.scheduling.schedule import Schedule

_STYLE_STAMP = Style(color=OD_COMMENT)
_STYLE_RUNNING = Style(color=OD_CYAN, bold=True)
_STYLE_NAME = Style(color=OD_FG, bold=True)
_STYLE_DONE = Style(color=OD_GREEN, bold=True)
_STYLE_FAIL = Style(color=OD_RED, bold=True)
_STYLE_SKIP = Style(color=OD_YELLOW, bold=True)
_STYLE_META = Style(color=OD_COMMENT)
_STYLE_OUT = Style(color=OD_FG)


def _stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _format_runtime(seconds: float | None) -> str:
    if seconds is None:
        return ""
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes, rem = divmod(seconds, 60)
    return f"{int(minutes)}m{rem:04.1f}s"


def _report_start(event: Event) -> None:
    line = Text()
    line.append(f"  {_stamp()}  ", style=_STYLE_STAMP)
    line.append("Running: ", style=_STYLE_RUNNING)
    line.append(event.summary(), style=_STYLE_NAME)
    Output().write(line)


def _report_finish(outcome: Outcome) -> None:
    summary = outcome.event.summary()
    stamp = _stamp()
    runtime = _format_runtime(outcome.runtime)
    out = Output()

    if outcome.skipped:
        line = Text()
        line.append(f"  {stamp}  ", style=_STYLE_STAMP)
        line.append("skipped: ", style=_STYLE_SKIP)
        line.append(summary, style=_STYLE_NAME)
        out.write(line)
        return

    if outcome.output and outcome.output.strip():
        for raw in outcome.output.rstrip().splitlines():
            body = Text()
            body.append("                     ", style=_STYLE_STAMP)
            body.append(raw, style=_STYLE_OUT)
            out.write(body)

    line = Text()
    line.append(f"  {stamp}  ", style=_STYLE_STAMP)
    if outcome.code != 0:
        line.append(f"{CROSS} ", style=_STYLE_FAIL)
        line.append(f"exit {outcome.code}: ", style=_STYLE_FAIL)
        line.append(summary, style=_STYLE_NAME)
    else:
        line.append(f"{CHECK} ", style=_STYLE_DONE)
        line.append("DONE  ", style=_STYLE_DONE)
        line.append(summary, style=_STYLE_NAME)
    if runtime:
        line.append(f"  {runtime}", style=_STYLE_META)
    out.write(line)


def _pick_task(events: Sequence[Event], name: str) -> Event | None:
    """Find the named task, or ask which one when nothing was named."""
    if name:
        for event in events:
            if name in (event.summary(), event.mutex_name(), event.description):
                return event
        return None
    if len(events) == 1:
        return events[0]
    from almasix.console.prompts import select

    labels = {index: event.summary() for index, event in enumerate(events)}
    return events[select("Which task would you like to run?", labels, default=0)]


class ScheduleCommand(Command):
    """Shared body: the schedule, and what runs a task's command."""

    def scheduler(self) -> tuple[Schedule, Runner]:
        """The schedule, and the runner that dispatches a task's command.

        ``routes/console.py`` is already loaded by the time a command runs, so
        the schedule is simply the one every ``schedule.…`` call built. Tasks
        go back through ``Smith``, which means a scheduled command is parsed
        and run exactly like a typed one.
        """
        from almasix.console.scheduling import schedule

        return schedule, self.call


class ScheduleRunCommand(ScheduleCommand):
    signature = "schedule:run"
    description = "Run the tasks that are due (wire this to cron, every minute)"

    def handle(self) -> int:
        from almasix.console.scheduling import run_schedule

        schedule, runner = self.scheduler()
        if not schedule.due_events() and not schedule.has_sub_minute_events():
            self.comment("No scheduled tasks are ready.")
            return self.SUCCESS

        outcomes = run_schedule(
            schedule,
            base_path=self.app.base_path,
            runner=runner,
            on_start=_report_start,
            on_finish=_report_finish,
        )
        if any(outcome.code != 0 and not outcome.skipped for outcome in outcomes):
            return self.FAILURE
        return self.SUCCESS


class ScheduleWorkCommand(ScheduleCommand):
    signature = "schedule:work {--sleep=60 : Seconds between ticks}"
    description = "Run the scheduler in the foreground, minute after minute"

    def handle(self) -> int:
        import time

        from almasix.console.scheduling import run_schedule

        given = self.option("sleep")
        try:
            sleep = int(str(given))
        except ValueError:
            self.error(f"Invalid value for '--sleep': {given!r} is not a valid integer.")
            return self.INVALID

        schedule, runner = self.scheduler()
        self.output.title("Schedule worker started")
        self.comment("  Press Ctrl-C to stop.")
        self.line()
        try:
            while True:
                run_schedule(
                    schedule,
                    base_path=self.app.base_path,
                    runner=runner,
                    on_start=_report_start,
                    on_finish=_report_finish,
                )
                time.sleep(max(1, sleep))
        except KeyboardInterrupt:
            self.line()
            self.output.label("Schedule worker stopped.")
        return self.SUCCESS


class ScheduleListCommand(ScheduleCommand):
    signature = "schedule:list {--timezone= : Show next run times in this timezone}"
    description = "List the scheduled tasks and when each next runs"

    def handle(self) -> int:
        from zoneinfo import ZoneInfo

        schedule, _ = self.scheduler()
        if not schedule.events:
            self.comment("No scheduled tasks are defined.")
            return self.SUCCESS

        timezone = str(self.option("timezone") or "")
        zone = ZoneInfo(timezone) if timezone else None
        rows = []
        for event in schedule.events:
            moment = event.next_run_at(datetime.now())
            if zone is not None:
                moment = (
                    moment.astimezone(zone)
                    if moment.tzinfo
                    else moment.astimezone().astimezone(zone)
                )
            rows.append(
                (
                    event.frequency(),
                    event.summary(),
                    event.description if event.description != event.summary() else "",
                    moment.strftime("%Y-%m-%d %H:%M:%S"),
                )
            )

        width = max(len(row[0]) for row in rows)
        self.output.label("Scheduled tasks")
        for frequency, summary, description, next_run in rows:
            line = Text()
            line.append(f"  {frequency:<{width}}  ", style=_STYLE_RUNNING)
            line.append(summary, style=_STYLE_NAME)
            if description:
                line.append(f"  ({description})", style=_STYLE_META)
            line.append("  next: ", style=_STYLE_META)
            line.append(next_run, style=_STYLE_DONE)
            self.output.write(line)
        return self.SUCCESS


class ScheduleTestCommand(ScheduleCommand):
    signature = "schedule:test {--name= : Run the task with this name or command}"
    description = "Run one scheduled task now, whatever its frequency says"

    def handle(self) -> int:
        from almasix.console.scheduling import run_task

        schedule, runner = self.scheduler()
        if not schedule.events:
            self.comment("No scheduled tasks are defined.")
            return self.SUCCESS

        name = str(self.option("name") or "")
        event = _pick_task(schedule.events, name)
        if event is None:
            line = Text()
            line.append(f"{CROSS} ", style=_STYLE_FAIL)
            line.append(f"No scheduled task matches {name!r}.", style=_STYLE_FAIL)
            self.output.write(line)
            return self.FAILURE

        _report_start(event)
        outcome = run_task(event, base_path=self.app.base_path, runner=runner)
        _report_finish(outcome)
        return outcome.code


class ScheduleInterruptCommand(ScheduleCommand):
    signature = "schedule:interrupt"
    description = "Stop an in-progress schedule:run at the end of this second"

    def handle(self) -> int:
        from almasix.console.scheduling import interrupt

        schedule, _ = self.scheduler()
        interrupt(base_path=self.app.base_path, store=schedule.cache_store)
        self.info("Interrupt signalled for the current minute.")
        return self.SUCCESS


class ScheduleClearCacheCommand(ScheduleCommand):
    signature = "schedule:clear-cache"
    description = "Release without-overlapping locks left behind by a stuck task"

    def handle(self) -> int:
        from almasix.console.scheduling import clear_cache

        schedule, _ = self.scheduler()
        cleared = clear_cache(schedule)
        if not cleared:
            self.comment("No scheduled task locks were held.")
            return self.SUCCESS
        for name in cleared:
            self.success(f"Released lock for: {name}")
        return self.SUCCESS
