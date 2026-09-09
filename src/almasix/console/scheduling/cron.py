"""Cron expressions — matching a moment, and finding the next one."""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta
from functools import lru_cache

_MONTHS = {
    name: number
    for number, name in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1
    )
}
_DAYS = {
    name: number for number, name in enumerate(("sun", "mon", "tue", "wed", "thu", "fri", "sat"), 0)
}


@lru_cache(maxsize=512)
def _fields(expression: str) -> tuple[str, str, str, str, str]:
    """The five fields of an expression, parsed once per expression."""
    parts = expression.split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {expression!r}")
    return (parts[0], parts[1], parts[2], parts[3], parts[4])


def cron_matches(expression: str, moment: datetime) -> bool:
    """Whether a five-field expression is due at ``moment``."""
    minute, hour, dom, month, dow = _fields(expression)
    return (
        field_matches(minute, moment.minute, 0, 59)
        and field_matches(hour, moment.hour, 0, 23)
        and _day_matches(dom, dow, moment)
        and field_matches(month, moment.month, 1, 12, names=_MONTHS)
    )


def field_matches(
    field: str,
    value: int,
    minimum: int,
    maximum: int,
    *,
    names: dict[str, int] | None = None,
) -> bool:
    """Whether one cron field admits ``value``."""
    for piece in field.split(","):
        if _piece_matches(piece.strip(), value, minimum, maximum, names):
            return True
    return False


def last_day_of_month(moment: datetime) -> int:
    """The last calendar day of the month ``moment`` falls in."""
    return calendar.monthrange(moment.year, moment.month)[1]


def next_run_at(expression: str, after: datetime, *, repeat_seconds: int | None = None) -> datetime:
    """The first moment at or after ``after`` when ``expression`` is due.

    Minutes are scanned rather than solved, which is exact for the five-field
    subset Almasix accepts and keeps ``schedule:list`` honest about leap years
    and month lengths. A year of minutes is the ceiling; beyond that the
    expression matches nothing reachable and ``after`` comes back unchanged.
    """
    if repeat_seconds:
        # A sub-minute task's next run is the next second it repeats on, which
        # is inside the minute it is already in.
        base = after.replace(microsecond=0)
        if cron_matches(expression, base):
            ahead = (repeat_seconds - base.second % repeat_seconds) % repeat_seconds
            candidate = base + timedelta(seconds=ahead)
            if candidate.minute == base.minute:
                return candidate
    moment = after.replace(second=0, microsecond=0)
    for _ in range(366 * 24 * 60):
        if moment > after and cron_matches(expression, moment):
            return moment
        moment += timedelta(minutes=1)
    return after


def _piece_matches(
    piece: str,
    value: int,
    minimum: int,
    maximum: int,
    names: dict[str, int] | None,
) -> bool:
    step = 1
    if "/" in piece:
        piece, _, step_text = piece.partition("/")
        step = int(step_text)
        if step <= 0:
            raise ValueError(f"Invalid cron step: {step_text!r}")
    if piece in ("*", "?"):
        start, end = minimum, maximum
    elif "-" in piece.lstrip("-"):
        start_text, _, end_text = piece.partition("-")
        start, end = _number(start_text, names), _number(end_text, names)
    else:
        start = end = _number(piece, names)
        if step == 1:
            return value == start
        end = maximum
    if not start <= value <= end:
        return False
    return (value - start) % step == 0


def _number(text: str, names: dict[str, int] | None) -> int:
    text = text.strip()
    if names is not None and text.lower() in names:
        return names[text.lower()]
    return int(text)


def _day_matches(dom: str, dow: str, moment: datetime) -> bool:
    """Day of month and day of week, with cron's either-or rule.

    When both fields are restricted, cron runs the task if *either* matches,
    which is what makes ``0 0 1 * mon`` mean "the first, and every Monday".
    """
    weekday = (moment.weekday() + 1) % 7  # 0 = Sunday
    dom_matches = field_matches(dom, moment.day, 1, 31)
    dow_matches = field_matches(dow, weekday, 0, 6, names=_DAYS) or (
        "7" in dow.split(",") and weekday == 0
    )
    if dom.strip() in ("*", "?"):
        return dow_matches
    if dow.strip() in ("*", "?"):
        return dom_matches
    return dom_matches or dow_matches


# The audit-era private names, kept because tests and the old module used them.
_cron_matches = cron_matches
_field_matches = field_matches


__all__ = [
    "cron_matches",
    "field_matches",
    "last_day_of_month",
    "next_run_at",
]
