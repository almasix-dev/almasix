"""Demo Chrono — Carbon-class dates and time travel (M53)."""

from __future__ import annotations

from almasix.chrono import Chrono, freeze, return_time
from almasix.console.command import Command
from almasix.support.helpers import now, today


class ProgressDatesCommand(Command):
    signature = "progress:dates"
    description = "Demo Chrono dates, helpers, and test time travel (M53)"

    def handle(self) -> int:
        self.info("Chrono — Carbon-class dates")
        moment = Chrono.parse("2024-06-15 14:30:00")
        self.line(f"  parse -> {moment.to_datetime_string()}")
        self.line(f"  add_days(5) -> {moment.add_days(5).to_date_string()}")
        self.line(f"  start_of_month -> {moment.start_of_month().to_date_string()}")
        self.line(f"  diff_for_humans -> {moment.sub_hours(3).diff_for_humans(moment)}")

        with freeze("2020-01-01 12:00:00"):
            self.line(f"  freeze now() -> {now().to_datetime_string()}")
            self.line(f"  freeze today() -> {today().to_date_string()}")
        return_time()
        self.line(f"  after return -> {Chrono.now().year} (wall clock)")

        self.info("chrono dates ok")
        return self.SUCCESS
