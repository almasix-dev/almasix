"""The schedule — where tasks are registered, and the shared attributes above them."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any

from almasix.console.scheduling.event import (
    FRIDAY,
    MONDAY,
    SATURDAY,
    SUNDAY,
    THURSDAY,
    TUESDAY,
    WEDNESDAY,
    Event,
    install_camel_aliases,
)

Callback = Callable[..., Any]

# Every fluent method a group can hold on behalf of its tasks.
_SHARED = (
    "cron",
    "every_second",
    "every_two_seconds",
    "every_five_seconds",
    "every_ten_seconds",
    "every_fifteen_seconds",
    "every_twenty_seconds",
    "every_thirty_seconds",
    "every_minute",
    "every_two_minutes",
    "every_three_minutes",
    "every_four_minutes",
    "every_five_minutes",
    "every_ten_minutes",
    "every_fifteen_minutes",
    "every_thirty_minutes",
    "hourly",
    "hourly_at",
    "every_odd_hour",
    "every_two_hours",
    "every_three_hours",
    "every_four_hours",
    "every_six_hours",
    "daily",
    "daily_at",
    "at",
    "twice_daily",
    "twice_daily_at",
    "days",
    "days_of_month",
    "weekly",
    "weekly_on",
    "monthly",
    "monthly_on",
    "twice_monthly",
    "last_day_of_month",
    "quarterly",
    "quarterly_on",
    "yearly",
    "yearly_on",
    "weekdays",
    "weekends",
    "sundays",
    "mondays",
    "tuesdays",
    "wednesdays",
    "thursdays",
    "fridays",
    "saturdays",
    "between",
    "unless_between",
    "when",
    "skip",
    "environments",
    "timezone",
    "even_in_maintenance_mode",
    "without_overlapping",
    "without_overlapping_lock",
    "on_one_server",
    "run_in_background",
    "send_output_to",
    "append_output_to",
    "email_output_to",
    "email_output_on_failure",
    "before",
    "after",
    "then",
    "on_success",
    "on_failure",
    "ping_before",
    "ping_before_if",
    "then_ping",
    "then_ping_if",
    "ping_on_success",
    "ping_on_success_if",
    "ping_on_failure",
    "ping_on_failure_if",
    "name",
)


def _shared_name(name: str) -> str | None:
    """The snake_case method a shared attribute name refers to, camel or not."""
    if name in _SHARED:
        return name
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return snake if snake in _SHARED else None


class PendingAttributes:
    """Attributes waiting for the tasks that will share them.

    Returned by frequency and constraint methods called on the schedule
    itself, so ``schedule.daily().on_one_server().group(...)`` configures
    every task the group defines.
    """

    def __init__(self, schedule: Schedule) -> None:
        self._schedule = schedule
        self._calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def group(self, callback: Callable[[], None]) -> None:
        """Define tasks that share these attributes."""
        self._schedule._push_group(self)
        try:
            callback()
        finally:
            self._schedule._pop_group()

    def apply_to(self, event: Event) -> None:
        """Replay the held attributes onto a task."""
        for method, args, kwargs in self._calls:
            getattr(event, method)(*args, **kwargs)

    def _record(self, method: str) -> Callable[..., PendingAttributes]:
        def held(*args: Any, **kwargs: Any) -> PendingAttributes:
            self._calls.append((method, args, kwargs))
            return self

        return held

    def __getattr__(self, name: str) -> Any:
        held = _shared_name(name)
        if held is not None:
            return self._record(held)
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")


class Schedule:
    """The registered tasks (Laravel ``Schedule``)."""

    SUNDAY = SUNDAY
    MONDAY = MONDAY
    TUESDAY = TUESDAY
    WEDNESDAY = WEDNESDAY
    THURSDAY = THURSDAY
    FRIDAY = FRIDAY
    SATURDAY = SATURDAY

    def __init__(self) -> None:
        self.events: list[Event] = []
        self.cache_store: str | None = None
        self._groups: list[PendingAttributes] = []

    # --- defining tasks ------------------------------------------------------

    def call(self, callback: Callback, description: str | None = None) -> Event:
        """Schedule a callable."""
        return self._add(
            Event(
                description=description or getattr(callback, "__name__", "call"),
                callback=callback,
            )
        )

    def command(self, signature: str, arguments: Iterable[str] | None = None) -> Event:
        """Schedule a Smith command, by name and arguments."""
        parts = [signature, *(str(argument) for argument in arguments or [])]
        line = " ".join(parts)
        return self._add(Event(description=line, command=line))

    def job(
        self,
        job: Any,
        queue: str | None = None,
        connection: str | None = None,
    ) -> Event:
        """Schedule a queued job, optionally onto a named queue or connection."""
        return self._add(
            Event(
                description=type(job).__name__,
                job=job,
                job_queue=queue,
                job_connection=connection,
            )
        )

    def exec(self, command: str) -> Event:
        """Schedule a shell command."""
        return self._add(Event(description=command, shell=command))

    def group(self, callback: Callable[[], None]) -> None:
        """Define tasks sharing no attributes — the empty group, for symmetry."""
        PendingAttributes(self).group(callback)

    def use_cache(self, store: str) -> Schedule:
        """Choose the cache store the scheduler takes its locks from."""
        self.cache_store = store
        return self

    # --- reading the schedule ------------------------------------------------

    def due_events(self, at: datetime | None = None) -> list[Event]:
        """The tasks the clock says are due."""
        moment = at or datetime.now()
        return [event for event in self.events if event.is_due(moment)]

    def has_sub_minute_events(self) -> bool:
        """Whether any task repeats within the minute."""
        return any(event.repeat_seconds for event in self.events)

    def clear(self) -> None:
        """Forget every task — used between tests."""
        self.events.clear()

    def _add(self, event: Event) -> Event:
        for group in self._groups:
            group.apply_to(event)
        self.events.append(event)
        return event

    def _push_group(self, attributes: PendingAttributes) -> None:
        self._groups.append(attributes)

    def _pop_group(self) -> None:
        self._groups.pop()

    def __getattr__(self, name: str) -> Any:
        # ``schedule.daily().group(...)`` — a frequency on the schedule itself
        # starts a set of shared attributes rather than a task.
        if _shared_name(name) is not None:
            return getattr(PendingAttributes(self), name)
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")


install_camel_aliases(Schedule)
install_camel_aliases(PendingAttributes)

# Process-wide schedule, which ``routes/console.py`` writes to.
schedule = Schedule()


__all__ = ["PendingAttributes", "Schedule", "schedule"]
