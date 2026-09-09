"""One scheduled task — its frequency, its constraints, and its hooks."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from almasix.aliases import install_camel_aliases
from almasix.console.scheduling.cron import cron_matches, last_day_of_month, next_run_at

Callback = Callable[..., Any]

SUNDAY = 0
MONDAY = 1
TUESDAY = 2
WEDNESDAY = 3
THURSDAY = 4
FRIDAY = 5
SATURDAY = 6

_DAY_NAMES = ("sundays", "mondays", "tuesdays", "wednesdays", "thursdays", "fridays", "saturdays")

# How far ahead ``next_run_at`` will look before giving up: a leap year of minutes.
_SCAN_LIMIT = 366 * 24 * 60

# Laravel's default: a without-overlapping lock lasts a day.
_DEFAULT_EXPIRY = 1440


class Event:
    """A scheduled task (Laravel ``Illuminate\\Console\\Scheduling\\Event``).

    Built by :class:`~almasix.console.scheduling.schedule.Schedule`, not
    directly: ``schedule.command("mail:digest").daily_at("02:00")``.
    """

    def __init__(
        self,
        description: str,
        callback: Callback | None = None,
        command: str | None = None,
        expression: str = "* * * * *",
        *,
        shell: str | None = None,
        job: Any | None = None,
        job_queue: str | None = None,
        job_connection: str | None = None,
    ) -> None:
        self.description = description
        self.callback = callback
        self.command = command
        self.shell = shell
        self.job = job
        self.job_queue = job_queue
        self.job_connection = job_connection
        self.expression = expression
        self.repeat_seconds: int | None = None

        self._name: str | None = None
        self._timezone: str | None = None
        self._time_filters: list[Callable[[datetime], bool]] = []
        self._when: list[Callback] = []
        self._skip: list[Callback] = []
        self._environments: list[str] | None = None

        self.prevents_overlapping = False
        self.overlapping_expires_at = _DEFAULT_EXPIRY
        self.runs_on_one_server = False
        self.runs_in_background = False
        self.runs_in_maintenance_mode = False

        self.output_path: str | None = None
        self.output_appends = False
        self.email_addresses: list[str] = []
        self.email_only_on_failure = False

        self.before_callbacks: list[Callback] = []
        self.after_callbacks: list[Callback] = []
        self.success_callbacks: list[Callback] = []
        self.failure_callbacks: list[Callback] = []

    def __repr__(self) -> str:
        return f"<Event {self.summary()!r} {self.expression!r}>"

    # --- identity ------------------------------------------------------------

    def name(self, name: str) -> Event:
        """Name the task, which is what its locks are keyed on."""
        self._name = name
        return self

    def purpose(self, description: str) -> Event:
        """Describe the task for ``schedule:list``."""
        self.description = description
        return self

    def summary(self) -> str:
        """A one-line label: what this task actually runs."""
        if self.command:
            return self.command
        if self.shell:
            return self.shell
        if self.job is not None:
            return type(self.job).__name__
        return self.description

    def mutex_name(self) -> str:
        """The lock identity for ``without_overlapping`` / ``on_one_server``."""
        return self._name or self.command or self.shell or self.description

    # --- frequency: seconds --------------------------------------------------

    def every_second(self) -> Event:
        return self._repeat_every(1)

    def every_two_seconds(self) -> Event:
        return self._repeat_every(2)

    def every_five_seconds(self) -> Event:
        return self._repeat_every(5)

    def every_ten_seconds(self) -> Event:
        return self._repeat_every(10)

    def every_fifteen_seconds(self) -> Event:
        return self._repeat_every(15)

    def every_twenty_seconds(self) -> Event:
        return self._repeat_every(20)

    def every_thirty_seconds(self) -> Event:
        return self._repeat_every(30)

    # --- frequency: minutes --------------------------------------------------

    def cron(self, expression: str) -> Event:
        """Run on a custom five-field expression."""
        self.expression = expression
        return self

    def every_minute(self) -> Event:
        return self._splice(1, "*")

    def every_two_minutes(self) -> Event:
        return self._splice(1, "*/2")

    def every_three_minutes(self) -> Event:
        return self._splice(1, "*/3")

    def every_four_minutes(self) -> Event:
        return self._splice(1, "*/4")

    def every_five_minutes(self) -> Event:
        return self._splice(1, "*/5")

    def every_ten_minutes(self) -> Event:
        return self._splice(1, "*/10")

    def every_fifteen_minutes(self) -> Event:
        return self._splice(1, "*/15")

    def every_thirty_minutes(self) -> Event:
        return self._splice(1, "0,30")

    # --- frequency: hours ----------------------------------------------------

    def hourly(self) -> Event:
        return self._splice(1, "0")

    def hourly_at(self, offset: int | Sequence[int]) -> Event:
        """Run at the given minute(s) past every hour."""
        return self._splice(1, _join(offset))

    def every_odd_hour(self, minutes: int | Sequence[int] = 0) -> Event:
        return self._splice(1, _join(minutes))._splice(2, "1-23/2")

    def every_two_hours(self, minutes: int | Sequence[int] = 0) -> Event:
        return self._splice(1, _join(minutes))._splice(2, "*/2")

    def every_three_hours(self, minutes: int | Sequence[int] = 0) -> Event:
        return self._splice(1, _join(minutes))._splice(2, "*/3")

    def every_four_hours(self, minutes: int | Sequence[int] = 0) -> Event:
        return self._splice(1, _join(minutes))._splice(2, "*/4")

    def every_six_hours(self, minutes: int | Sequence[int] = 0) -> Event:
        return self._splice(1, _join(minutes))._splice(2, "*/6")

    # --- frequency: days -----------------------------------------------------

    def daily(self) -> Event:
        return self._splice(1, "0")._splice(2, "0")

    def daily_at(self, time: str) -> Event:
        """Run every day at ``HH:MM``."""
        hour, minute = _parse_time(time)
        return self._splice(1, str(minute))._splice(2, str(hour))

    # Laravel spells the same thing ``at`` when a frequency is already set.
    def at(self, time: str) -> Event:
        return self.daily_at(time)

    def twice_daily(self, first: int = 1, second: int = 13) -> Event:
        return self.twice_daily_at(first, second, 0)

    def twice_daily_at(self, first: int = 1, second: int = 13, offset: int = 0) -> Event:
        return self._splice(1, str(offset))._splice(2, f"{first},{second}")

    def days(self, *days: int | str | Iterable[int | str]) -> Event:
        """Limit the task to the given days of the week (0 = Sunday)."""
        return self._splice(5, _join(_flatten(days)))

    def days_of_month(self, *days: int | Iterable[int]) -> Event:
        """Limit the task to the given days of the month."""
        return self._splice(3, _join(_flatten(days)))

    # --- frequency: weeks, months, quarters, years ---------------------------

    def weekly(self) -> Event:
        return self.daily()._splice(5, "0")

    def weekly_on(self, day: int | str | Sequence[int | str], time: str = "0:0") -> Event:
        return self.daily_at(time)._splice(5, _join(day))

    def monthly(self) -> Event:
        return self.daily()._splice(3, "1")

    def monthly_on(self, day: int = 1, time: str = "0:0") -> Event:
        return self.daily_at(time)._splice(3, str(day))

    def twice_monthly(self, first: int = 1, second: int = 16, time: str = "0:0") -> Event:
        return self.daily_at(time)._splice(3, f"{first},{second}")

    def last_day_of_month(self, time: str = "0:0") -> Event:
        """Run on the month's final day, whatever length the month is."""
        self.daily_at(time)
        self._time_filters.append(lambda moment: moment.day == last_day_of_month(moment))
        return self

    def quarterly(self) -> Event:
        return self.daily()._splice(3, "1")._splice(4, "1-12/3")

    def quarterly_on(self, day: int = 1, time: str = "0:0") -> Event:
        return self.daily_at(time)._splice(3, str(day))._splice(4, "1-12/3")

    def yearly(self) -> Event:
        return self.monthly()._splice(4, "1")

    def yearly_on(self, month: int = 1, day: int | str = 1, time: str = "0:0") -> Event:
        return self.daily_at(time)._splice(3, str(day))._splice(4, str(month))

    # --- constraints: days ---------------------------------------------------

    def weekdays(self) -> Event:
        return self.days(MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY)

    def weekends(self) -> Event:
        return self.days(SATURDAY, SUNDAY)

    # --- constraints: time, truth, environment -------------------------------

    def between(self, start: str, end: str) -> Event:
        """Only run between two times of day, inclusive of both ends."""
        self._time_filters.append(lambda moment: _between(moment, start, end))
        return self

    def unless_between(self, start: str, end: str) -> Event:
        """Never run between two times of day."""
        self._time_filters.append(lambda moment: not _between(moment, start, end))
        return self

    def when(self, condition: Callback | bool) -> Event:
        """Run only when the condition holds."""
        self._when.append(condition if callable(condition) else (lambda: condition))
        return self

    def skip(self, condition: Callback | bool) -> Event:
        """Skip the run when the condition holds — the inverse of ``when``."""
        self._skip.append(condition if callable(condition) else (lambda: condition))
        return self

    def environments(self, *names: str | Iterable[str]) -> Event:
        """Run only in the named environments (``APP_ENV``)."""
        self._environments = [str(name) for name in _flatten(names)]
        return self

    def timezone(self, timezone: str) -> Event:
        """Interpret this task's times in ``timezone``."""
        self._timezone = timezone
        return self

    def even_in_maintenance_mode(self) -> Event:
        """Run even while the application is down for maintenance."""
        self.runs_in_maintenance_mode = True
        return self

    # --- execution modes -----------------------------------------------------

    def without_overlapping(self, expires_at: int = _DEFAULT_EXPIRY) -> Event:
        """Skip the run when the previous one is still going.

        ``expires_at`` is in minutes, and bounds how long a crashed run can
        keep the lock: after it, the task is allowed to start again.
        """
        self.prevents_overlapping = True
        self.overlapping_expires_at = expires_at
        return self

    # M9 named it this; Laravel's own spelling arrives by the camelCase alias.
    def without_overlapping_lock(self, expires_at: int = _DEFAULT_EXPIRY) -> Event:
        return self.without_overlapping(expires_at)

    def on_one_server(self) -> Event:
        """Run on whichever server claims it first, not on all of them."""
        self.runs_on_one_server = True
        return self

    def run_in_background(self) -> Event:
        """Run alongside the other due tasks instead of holding up the queue."""
        self.runs_in_background = True
        return self

    # --- output --------------------------------------------------------------

    def send_output_to(self, path: str, append: bool = False) -> Event:
        """Write the task's output to a file."""
        self.output_path = str(path)
        self.output_appends = append
        return self

    def append_output_to(self, path: str) -> Event:
        """Append the task's output to a file."""
        return self.send_output_to(path, append=True)

    def email_output_to(self, addresses: str | Iterable[str]) -> Event:
        """Email the task's output."""
        self.email_addresses = [str(address) for address in _flatten([addresses])]
        self.email_only_on_failure = False
        return self

    def email_output_on_failure(self, addresses: str | Iterable[str]) -> Event:
        """Email the task's output only when it exits non-zero."""
        self.email_output_to(addresses)
        self.email_only_on_failure = True
        return self

    # --- hooks ---------------------------------------------------------------

    def before(self, callback: Callback) -> Event:
        """Run a callback before the task."""
        self.before_callbacks.append(callback)
        return self

    def after(self, callback: Callback) -> Event:
        """Run a callback after the task, whatever it exited with."""
        self.after_callbacks.append(callback)
        return self

    def then(self, callback: Callback) -> Event:
        return self.after(callback)

    def on_success(self, callback: Callback) -> Event:
        """Run a callback when the task exits zero."""
        self.success_callbacks.append(callback)
        return self

    def on_failure(self, callback: Callback) -> Event:
        """Run a callback when the task exits non-zero."""
        self.failure_callbacks.append(callback)
        return self

    def ping_before(self, url: str) -> Event:
        """GET a URL before the task runs."""
        return self.before(lambda: _ping(url))

    def ping_before_if(self, condition: Any, url: str) -> Event:
        return self.ping_before(url) if _truthy(condition) else self

    def then_ping(self, url: str) -> Event:
        """GET a URL after the task runs."""
        return self.after(lambda: _ping(url))

    def then_ping_if(self, condition: Any, url: str) -> Event:
        return self.then_ping(url) if _truthy(condition) else self

    def ping_on_success(self, url: str) -> Event:
        """GET a URL when the task exits zero."""
        return self.on_success(lambda: _ping(url))

    def ping_on_success_if(self, condition: Any, url: str) -> Event:
        return self.ping_on_success(url) if _truthy(condition) else self

    def ping_on_failure(self, url: str) -> Event:
        """GET a URL when the task exits non-zero."""
        return self.on_failure(lambda: _ping(url))

    def ping_on_failure_if(self, condition: Any, url: str) -> Event:
        return self.ping_on_failure(url) if _truthy(condition) else self

    # --- due, and allowed to run ---------------------------------------------

    def is_due(self, at: datetime | None = None) -> bool:
        """Whether the clock says this task should run."""
        moment = self._moment(at)
        if not cron_matches(self.expression, moment):
            return False
        return all(predicate(moment) for predicate in self._time_filters)

    def filters_pass(self) -> bool:
        """Whether the ``when`` / ``skip`` / ``environments`` tests allow the run."""
        if self._environments is not None and _environment() not in self._environments:
            return False
        if not all(_call(condition) for condition in self._when):
            return False
        return not any(_call(condition) for condition in self._skip)

    def should_repeat_now(self, at: datetime | None = None) -> bool:
        """Whether a sub-minute task is due this second."""
        if not self.repeat_seconds:
            return False
        return self._moment(at).second % self.repeat_seconds == 0

    def next_run_at(self, after: datetime | None = None) -> datetime:
        """When this task is next due, in the task's own timezone.

        Minutes are scanned rather than solved, so the answer respects the
        ``between`` / ``last_day_of_month`` style constraints as well as the
        expression. A year with no match returns the moment asked about.
        """
        moment = self._moment(after)
        if self.repeat_seconds:
            candidate = next_run_at(self.expression, moment, repeat_seconds=self.repeat_seconds)
            if candidate.minute == moment.minute:
                return candidate
        candidate = moment.replace(second=0, microsecond=0)
        for _ in range(_SCAN_LIMIT):
            candidate += timedelta(minutes=1)
            if self.is_due(candidate):
                return candidate
        return moment

    def frequency(self) -> str:
        """A human label for the schedule, for ``schedule:list``."""
        if self.repeat_seconds:
            unit = "second" if self.repeat_seconds == 1 else f"{self.repeat_seconds} seconds"
            return f"every {unit}"
        return self.expression

    # --- internals -----------------------------------------------------------

    def _repeat_every(self, seconds: int) -> Event:
        self.repeat_seconds = seconds
        return self.every_minute()

    def _splice(self, position: int, value: str) -> Event:
        fields = self.expression.split()
        fields[position - 1] = value
        self.expression = " ".join(fields)
        return self

    def _moment(self, at: datetime | None) -> datetime:
        moment = at or datetime.now()
        if self._timezone is None:
            return moment
        zone = ZoneInfo(self._timezone)
        if moment.tzinfo is None:
            moment = moment.astimezone()
        return moment.astimezone(zone)


def _parse_time(time: str | int) -> tuple[int, int]:
    """``'13:30'`` / ``'13'`` / ``13`` → ``(13, 30)`` / ``(13, 0)``."""
    text = str(time).strip()
    hour, _, minute = text.partition(":")
    return int(hour or 0), int(minute or 0)


def _between(moment: datetime, start: str, end: str) -> bool:
    start_at = _at_time(moment, start)
    end_at = _at_time(moment, end)
    if end_at < start_at:
        # A window that crosses midnight, such as 23:00 to 04:00.
        return moment >= start_at or moment <= end_at
    return start_at <= moment <= end_at


def _at_time(moment: datetime, time: str) -> datetime:
    hour, minute = _parse_time(time)
    return moment.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _join(value: Any) -> str:
    if isinstance(value, (str, int)):
        return str(value)
    return ",".join(str(item) for item in value)


def _flatten(values: Iterable[Any]) -> list[Any]:
    """One level of nesting undone, so ``days(0, 3)`` and ``days([0, 3])`` agree."""
    flattened: list[Any] = []
    for value in values:
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            flattened.extend(_flatten(value))
        else:
            flattened.append(value)
    return flattened


def _truthy(condition: Any) -> bool:
    return bool(condition() if callable(condition) else condition)


def _call(condition: Callback) -> bool:
    return bool(condition())


def _environment() -> str:
    from almasix.config import config

    try:
        return str(config("app.env", "production"))
    except Exception:  # pragma: no cover - config is absent outside an app
        return "production"


def _ping(url: str) -> None:
    """GET a URL, ignoring the answer — the point is that it was called."""
    from almasix.client import Http

    try:
        Http.get(url)
    except Exception:  # pragma: no cover - a ping must not fail the task
        pass


def call_hook(callback: Callback, output: str | None) -> Any:
    """Invoke a hook, handing it the task output when it asks for one."""
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):  # pragma: no cover - builtins
        return callback()
    wants_output = any(
        parameter.kind
        in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD, parameter.VAR_POSITIONAL)
        and parameter.default is parameter.empty
        for parameter in signature.parameters.values()
    )
    if not wants_output:
        return callback()
    from almasix.support import str_

    return callback(str_(output or ""))


install_camel_aliases(Event)

# ``mondays()`` … ``sundays()``, which are ``days(N)`` with a name.
for _index, _method_name in enumerate(_DAY_NAMES):

    def _day_method(self: Event, _day: int = _index) -> Event:
        return self.days(_day)

    _day_method.__name__ = _method_name
    _day_method.__doc__ = f"Limit the task to {_method_name[:-1].title()}."
    setattr(Event, _method_name, _day_method)


__all__ = [
    "FRIDAY",
    "MONDAY",
    "SATURDAY",
    "SUNDAY",
    "THURSDAY",
    "TUESDAY",
    "WEDNESDAY",
    "Event",
    "call_hook",
    "install_camel_aliases",
]
