"""The ``schedule:*`` commands — run, work, list, test, interrupt, clear-cache.

Cron calls ``schedule:run`` every minute; everything else here is for the
person at the keyboard, asking what is scheduled, running one task now, or
clearing up after a stuck one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import typer

from avalon.console.command import Command

if TYPE_CHECKING:
    from collections.abc import Sequence

    from avalon.console.scheduling.event import Event
    from avalon.console.scheduling.runner import Outcome, Runner
    from avalon.console.scheduling.schedule import Schedule


def _report_start(event: Event) -> None:
    typer.echo(f"Running: {event.summary()}")


def _report_finish(outcome: Outcome) -> None:
    if outcome.skipped:
        typer.secho(f"  skipped: {outcome.event.summary()}", fg=typer.colors.YELLOW)
    elif outcome.code != 0:
        _red(f"  exit {outcome.code}: {outcome.event.summary()}")


def _red(message: str) -> None:
    """Red on **stdout**.

    ``self.error()`` writes to stderr; the schedule's failure lines have always
    gone to stdout, next to the ``Running:`` line they belong to.
    """
    typer.secho(message, fg=typer.colors.RED)


def _pick_task(events: Sequence[Event], name: str) -> Event | None:
    """Find the named task, or ask which one when nothing was named."""
    if name:
        for event in events:
            if name in (event.summary(), event.mutex_name(), event.description):
                return event
        return None
    if len(events) == 1:
        return events[0]
    from avalon.console.prompts import select

    labels = {index: event.summary() for index, event in enumerate(events)}
    return events[select("Which task would you like to run?", labels, default=0)]


class ScheduleCommand(Command):
    """Shared body: the schedule, and what runs a task's command."""

    def scheduler(self) -> tuple[Schedule, Runner]:
        """The schedule, and the runner that dispatches a task's command.

        ``routes/console.py`` is already loaded by the time a command runs, so
        the schedule is simply the one every ``schedule.…`` call built. Tasks
        go back through ``Artisan``, which means a scheduled command is parsed
        and run exactly like a typed one.
        """
        from avalon.console.scheduling import schedule

        return schedule, self.call


class ScheduleRunCommand(ScheduleCommand):
    signature = "schedule:run"
    description = "Run the tasks that are due (wire this to cron, every minute)"

    def handle(self) -> int:
        from avalon.console.scheduling import run_schedule

        schedule, runner = self.scheduler()
        if not schedule.due_events() and not schedule.has_sub_minute_events():
            self.line("No scheduled tasks are ready.")
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

        from avalon.console.scheduling import run_schedule

        given = self.option("sleep")
        try:
            sleep = int(str(given))
        except ValueError:
            self.error(f"Invalid value for '--sleep': {given!r} is not a valid integer.")
            return self.INVALID

        schedule, runner = self.scheduler()
        self.line("Schedule worker started. Press Ctrl-C to stop.")
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
            self.line("Schedule worker stopped.")
        return self.SUCCESS


class ScheduleListCommand(ScheduleCommand):
    signature = "schedule:list {--timezone= : Show next run times in this timezone}"
    description = "List the scheduled tasks and when each next runs"

    def handle(self) -> int:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        schedule, _ = self.scheduler()
        if not schedule.events:
            self.line("No scheduled tasks are defined.")
            return self.SUCCESS

        timezone = str(self.option("timezone") or "")
        zone = ZoneInfo(timezone) if timezone else None
        rows = []
        for event in schedule.events:
            moment = event.next_run_at(datetime.now())
            if zone is not None:
                moment = (
                    moment.astimezone(zone) if moment.tzinfo else moment.astimezone().astimezone(zone)
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
        for frequency, summary, description, next_run in rows:
            suffix = f"  ({description})" if description else ""
            self.line(f"  {frequency:<{width}}  {summary}{suffix}  next: {next_run}")
        return self.SUCCESS


class ScheduleTestCommand(ScheduleCommand):
    signature = "schedule:test {--name= : Run the task with this name or command}"
    description = "Run one scheduled task now, whatever its frequency says"

    def handle(self) -> int:
        from avalon.console.scheduling import run_task

        schedule, runner = self.scheduler()
        if not schedule.events:
            self.line("No scheduled tasks are defined.")
            return self.SUCCESS

        name = str(self.option("name") or "")
        event = _pick_task(schedule.events, name)
        if event is None:
            _red(f"No scheduled task matches {name!r}.")
            return self.FAILURE

        self.line(f"Running: {event.summary()}")
        outcome = run_task(event, base_path=self.app.base_path, runner=runner)
        if outcome.output:
            self.line(outcome.output.rstrip())
        return outcome.code


class ScheduleInterruptCommand(ScheduleCommand):
    signature = "schedule:interrupt"
    description = "Stop an in-progress schedule:run at the end of this second"

    def handle(self) -> int:
        from avalon.console.scheduling import interrupt

        schedule, _ = self.scheduler()
        interrupt(base_path=self.app.base_path, store=schedule.cache_store)
        self.line("Interrupt signalled for the current minute.")
        return self.SUCCESS


class ScheduleClearCacheCommand(ScheduleCommand):
    signature = "schedule:clear-cache"
    description = "Release without-overlapping locks left behind by a stuck task"

    def handle(self) -> int:
        from avalon.console.scheduling import clear_cache

        schedule, _ = self.scheduler()
        cleared = clear_cache(schedule)
        if not cleared:
            self.line("No scheduled task locks were held.")
            return self.SUCCESS
        for name in cleared:
            self.line(f"Released lock for: {name}")
        return self.SUCCESS
