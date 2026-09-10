"""Demo the scheduler: frequencies, constraints, hooks, and the runner (M31)."""

from __future__ import annotations

from datetime import datetime

from almasix.console.command import Command
from almasix.console.scheduling import Schedule, ScheduledTaskSkipped, run_due_events
from almasix.events import Event as Bus


class ProgressScheduleCommand(Command):
    signature = "progress:schedule"
    description = "Demo the scheduler's frequencies, constraints, hooks, and tick (M31)"

    def handle(self) -> int:
        schedule = Schedule()

        # A frequency writes cron fields, so they combine rather than replace.
        report = schedule.command("progress:hello").weekdays().hourly().between("8:00", "17:00")
        self.info(f"weekday office hours → {report.expression} + a between() window")
        self.info(
            f"quarterly on the 4th at 14:00 → {schedule.command('x').quarterly_on(4, '14:00').expression}"
        )

        # last_day_of_month asks the calendar, so February is right too.
        month_end = schedule.command("y").last_day_of_month("15:00")
        self.info(f"last day of February 2027 → {month_end.is_due(datetime(2027, 2, 28, 15, 0))}")

        # A sub-minute task repeats inside the minute cron cannot reach into.
        pulse = schedule.command("z").every_ten_seconds()
        self.info(
            f"every ten seconds → repeats at :{pulse.repeat_seconds}s, cron {pulse.expression}"
        )

        self.new_line()
        self.comment("A tick: what runs, what is turned away, and the hooks around it")

        seen: list[str] = []
        ran = Schedule()
        ran.call(lambda: seen.append("task"), description="digest").every_minute().before(
            lambda: seen.append("before")
        ).on_success(lambda: seen.append("success"))
        ran.call(lambda: seen.append("never"), description="paused").every_minute().skip(
            lambda: True
        )
        ran.exec("echo shell-task-output").every_minute()

        skipped: list[str] = []
        Bus.listen(ScheduledTaskSkipped, lambda event: skipped.append(event.reason))

        outcomes = run_due_events(ran, base_path=self.app.base_path, at=datetime.now())

        self.info(f"hooks → {seen}")
        self.info(f"turned away → {skipped}")
        for outcome in outcomes:
            state = "skipped" if outcome.skipped else f"exit {outcome.code}"
            self.line(f"  {outcome.event.summary():<32} {state} {outcome.output.strip()}")

        self.new_line()
        self.comment("Run `smith schedule:list` to see this app's real schedule")
        self.success("schedule demo ok")
        return 0
