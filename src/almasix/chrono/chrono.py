"""``Chrono`` — immutable-friendly fluent datetime (Carbon-class).

``Chrono`` subclasses :class:`datetime.datetime` so it drops into APIs that
expect a stdlib datetime (ORM bindings, comparisons, ``isoformat``). Every
mutating-looking method returns a **new** ``Chrono``.
"""

from __future__ import annotations

import calendar
import re
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from email.utils import parsedate_to_datetime
from typing import Any, Self
from zoneinfo import ZoneInfo

_TEST_NOW: Chrono | None = None

_UNITS = {
    "year": "years",
    "years": "years",
    "month": "months",
    "months": "months",
    "week": "weeks",
    "weeks": "weeks",
    "day": "days",
    "days": "days",
    "hour": "hours",
    "hours": "hours",
    "minute": "minutes",
    "minutes": "minutes",
    "second": "seconds",
    "seconds": "seconds",
    "microsecond": "microseconds",
    "microseconds": "microseconds",
}


class Chrono(datetime):
    """Carbon-class fluent date/time."""

    # --- construction --------------------------------------------------------

    def __new__(
        cls,
        year: int,
        month: int,
        day: int,
        hour: int = 0,
        minute: int = 0,
        second: int = 0,
        microsecond: int = 0,
        tzinfo: tzinfo | None = UTC,
        *,
        fold: int = 0,
    ) -> Self:
        return datetime.__new__(
            cls,
            year,
            month,
            day,
            hour,
            minute,
            second,
            microsecond,
            tzinfo or UTC,
            fold=fold,
        )

    @classmethod
    def instance(cls, value: datetime | date | Self) -> Self:
        """Wrap a datetime/date (or return ``value`` when already a Chrono)."""
        if isinstance(value, cls):
            return value
        if isinstance(value, datetime):
            tz = value.tzinfo or UTC
            return cls(
                value.year,
                value.month,
                value.day,
                value.hour,
                value.minute,
                value.second,
                value.microsecond,
                tz,
                fold=value.fold,
            )
        if isinstance(value, date):
            return cls(value.year, value.month, value.day, tzinfo=UTC)
        raise TypeError(f"Cannot create Chrono from {type(value)!r}.")

    @classmethod
    def now(cls, tz: tzinfo | str | None = None) -> Self:
        zone = _resolve_tz(tz)
        if _TEST_NOW is not None:
            frozen = _TEST_NOW if _TEST_NOW.tzinfo else _TEST_NOW.replace(tzinfo=UTC)
            return cls.instance(frozen.astimezone(zone))
        return cls.instance(datetime.now(zone))

    @classmethod
    def utcnow(cls) -> Self:
        return cls.now(UTC)

    @classmethod
    def today(cls, tz: tzinfo | str | None = None) -> Self:
        return cls.now(tz).start_of_day()

    @classmethod
    def tomorrow(cls, tz: tzinfo | str | None = None) -> Self:
        return cls.today(tz).add_days(1)

    @classmethod
    def yesterday(cls, tz: tzinfo | str | None = None) -> Self:
        return cls.today(tz).sub_days(1)

    @classmethod
    def create(
        cls,
        year: int | None = None,
        month: int | None = None,
        day: int | None = None,
        hour: int = 0,
        minute: int = 0,
        second: int = 0,
        microsecond: int = 0,
        tz: tzinfo | str | None = None,
    ) -> Self:
        base = cls.now(tz)
        return cls(
            year if year is not None else base.year,
            month if month is not None else base.month,
            day if day is not None else base.day,
            hour,
            minute,
            second,
            microsecond,
            _resolve_tz(tz) if tz is not None else base.tzinfo,
        )

    @classmethod
    def create_from_format(cls, fmt: str, value: str, tz: tzinfo | str | None = None) -> Self:
        parsed = datetime.strptime(value, fmt)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_resolve_tz(tz))
        elif tz is not None:
            parsed = parsed.astimezone(_resolve_tz(tz))
        return cls.instance(parsed)

    @classmethod
    def parse(cls, value: str | datetime | date | int | float | Self, tz: tzinfo | str | None = None) -> Self:
        """Parse many common inputs into a Chrono."""
        if isinstance(value, cls):
            return value if tz is None else value.set_timezone(tz)
        if isinstance(value, datetime):
            inst = cls.instance(value)
            return inst if tz is None else inst.set_timezone(tz)
        if isinstance(value, date) and not isinstance(value, datetime):
            inst = cls(value.year, value.month, value.day, tzinfo=_resolve_tz(tz))
            return inst
        if isinstance(value, (int, float)):
            return cls.fromtimestamp(float(value), tz=_resolve_tz(tz))
        text = str(value).strip()
        if not text:
            raise ValueError("Cannot parse an empty date string.")
        lowered = text.lower()
        if lowered in {"now"}:
            return cls.now(tz)
        if lowered in {"today"}:
            return cls.today(tz)
        if lowered in {"tomorrow"}:
            return cls.tomorrow(tz)
        if lowered in {"yesterday"}:
            return cls.yesterday(tz)
        # Relative phrases via datetime's parser are limited — handle a few.
        relative = _try_relative(text, tz)
        if relative is not None:
            return relative
        try:
            return cls.instance(parsedate_to_datetime(text))
        except (TypeError, ValueError, IndexError):
            pass
        # ISO-8601 and common variants.
        cleaned = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(cleaned)
        except ValueError:
            match = re.match(
                r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?$",
                text,
            )
            if not match:
                raise ValueError(f"Unable to parse date [{text}].") from None
            y, m, d, h, mi, s = match.groups()
            parsed = datetime(
                int(y),
                int(m),
                int(d),
                int(h or 0),
                int(mi or 0),
                int(s or 0),
                tzinfo=_resolve_tz(tz),
            )
            return cls.instance(parsed)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_resolve_tz(tz))
        elif tz is not None:
            parsed = parsed.astimezone(_resolve_tz(tz))
        return cls.instance(parsed)

    @classmethod
    def fromtimestamp(cls, timestamp: float, tz: tzinfo | str | None = None) -> Self:  # noqa: N802
        return cls.instance(datetime.fromtimestamp(timestamp, tz=_resolve_tz(tz)))

    # --- test clock ----------------------------------------------------------

    @classmethod
    def set_test_now(cls, moment: datetime | Self | None) -> None:
        global _TEST_NOW
        _TEST_NOW = None if moment is None else cls.instance(moment)

    @classmethod
    def get_test_now(cls) -> Self | None:
        return _TEST_NOW

    @classmethod
    def has_test_now(cls) -> bool:
        return _TEST_NOW is not None

    # --- copy / timezone -----------------------------------------------------

    def copy(self) -> Self:
        return type(self)(
            self.year,
            self.month,
            self.day,
            self.hour,
            self.minute,
            self.second,
            self.microsecond,
            self.tzinfo,
            fold=self.fold,
        )

    def clone(self) -> Self:
        return self.copy()

    def timezone(self, tz: tzinfo | str) -> Self:
        """Return a copy with the wall clock rewritten into ``tz`` (keep fields)."""
        zone = _resolve_tz(tz)
        return type(self)(
            self.year,
            self.month,
            self.day,
            self.hour,
            self.minute,
            self.second,
            self.microsecond,
            zone,
            fold=self.fold,
        )

    def set_timezone(self, tz: tzinfo | str) -> Self:
        """Convert the instant into ``tz`` (same moment, new offset)."""
        return type(self).instance(self.astimezone(_resolve_tz(tz)))

    def utc(self) -> Self:
        return self.set_timezone(UTC)

    # --- add / sub -----------------------------------------------------------

    def add(self, **units: float) -> Self:
        result: Chrono = self
        for key, amount in units.items():
            canon = _UNITS.get(key)
            if canon is None:
                raise ValueError(f"Unknown unit [{key}].")
            result = getattr(result, f"add_{canon}")(amount)
        return type(self).instance(result)

    def sub(self, **units: float) -> Self:
        return self.add(**{k: -v for k, v in units.items()})

    def add_years(self, years: float = 1) -> Self:
        return self.add_months(years * 12)

    def sub_years(self, years: float = 1) -> Self:
        return self.add_years(-years)

    def add_months(self, months: float = 1) -> Self:
        whole = int(months)
        year = self.year + (self.month - 1 + whole) // 12
        month = (self.month - 1 + whole) % 12 + 1
        day = min(self.day, calendar.monthrange(year, month)[1])
        base = type(self)(
            year,
            month,
            day,
            self.hour,
            self.minute,
            self.second,
            self.microsecond,
            self.tzinfo,
            fold=self.fold,
        )
        frac = months - whole
        if frac:
            days = calendar.monthrange(base.year, base.month)[1] * frac
            return base.add_days(days)
        return base

    def sub_months(self, months: float = 1) -> Self:
        return self.add_months(-months)

    def add_weeks(self, weeks: float = 1) -> Self:
        return self.add_days(weeks * 7)

    def sub_weeks(self, weeks: float = 1) -> Self:
        return self.add_weeks(-weeks)

    def add_days(self, days: float = 1) -> Self:
        return type(self).instance(datetime.__add__(self, timedelta(days=days)))

    def sub_days(self, days: float = 1) -> Self:
        return self.add_days(-days)

    def add_hours(self, hours: float = 1) -> Self:
        return type(self).instance(datetime.__add__(self, timedelta(hours=hours)))

    def sub_hours(self, hours: float = 1) -> Self:
        return self.add_hours(-hours)

    def add_minutes(self, minutes: float = 1) -> Self:
        return type(self).instance(datetime.__add__(self, timedelta(minutes=minutes)))

    def sub_minutes(self, minutes: float = 1) -> Self:
        return self.add_minutes(-minutes)

    def add_seconds(self, seconds: float = 1) -> Self:
        return type(self).instance(datetime.__add__(self, timedelta(seconds=seconds)))

    def sub_seconds(self, seconds: float = 1) -> Self:
        return self.add_seconds(-seconds)

    def add_microseconds(self, microseconds: float = 1) -> Self:
        return type(self).instance(datetime.__add__(self, timedelta(microseconds=microseconds)))

    def sub_microseconds(self, microseconds: float = 1) -> Self:
        return self.add_microseconds(-microseconds)

    def __add__(self, other: Any) -> Any:
        result = datetime.__add__(self, other)
        return type(self).instance(result) if isinstance(result, datetime) else result

    def __sub__(self, other: Any) -> Any:
        result = datetime.__sub__(self, other)
        if isinstance(result, datetime):
            return type(self).instance(result)
        return result

    # --- boundaries ----------------------------------------------------------

    def start_of_day(self) -> Self:
        return type(self)(self.year, self.month, self.day, 0, 0, 0, 0, self.tzinfo)

    def end_of_day(self) -> Self:
        return type(self)(self.year, self.month, self.day, 23, 59, 59, 999999, self.tzinfo)

    def start_of_hour(self) -> Self:
        return type(self)(self.year, self.month, self.day, self.hour, 0, 0, 0, self.tzinfo)

    def end_of_hour(self) -> Self:
        return type(self)(self.year, self.month, self.day, self.hour, 59, 59, 999999, self.tzinfo)

    def start_of_minute(self) -> Self:
        return type(self)(
            self.year, self.month, self.day, self.hour, self.minute, 0, 0, self.tzinfo
        )

    def end_of_minute(self) -> Self:
        return type(self)(
            self.year, self.month, self.day, self.hour, self.minute, 59, 999999, self.tzinfo
        )

    def start_of_month(self) -> Self:
        return type(self)(self.year, self.month, 1, 0, 0, 0, 0, self.tzinfo)

    def end_of_month(self) -> Self:
        last = calendar.monthrange(self.year, self.month)[1]
        return type(self)(self.year, self.month, last, 23, 59, 59, 999999, self.tzinfo)

    def start_of_year(self) -> Self:
        return type(self)(self.year, 1, 1, 0, 0, 0, 0, self.tzinfo)

    def end_of_year(self) -> Self:
        return type(self)(self.year, 12, 31, 23, 59, 59, 999999, self.tzinfo)

    def start_of_week(self, week_starts_at: int = 0) -> Self:
        """Monday=0 … Sunday=6 (Python's ``weekday()``)."""
        delta = (self.weekday() - week_starts_at) % 7
        return self.sub_days(delta).start_of_day()

    def end_of_week(self, week_starts_at: int = 0) -> Self:
        return self.start_of_week(week_starts_at).add_days(6).end_of_day()

    def start_of_quarter(self) -> Self:
        month = ((self.month - 1) // 3) * 3 + 1
        return type(self)(self.year, month, 1, 0, 0, 0, 0, self.tzinfo)

    def end_of_quarter(self) -> Self:
        return self.start_of_quarter().add_months(3).sub_microseconds(1)

    def start_of_decade(self) -> Self:
        year = (self.year // 10) * 10
        return type(self)(year, 1, 1, 0, 0, 0, 0, self.tzinfo)

    def end_of_decade(self) -> Self:
        return self.start_of_decade().add_years(10).sub_microseconds(1)

    def start_of_century(self) -> Self:
        year = ((self.year - 1) // 100) * 100 + 1
        return type(self)(year, 1, 1, 0, 0, 0, 0, self.tzinfo)

    def end_of_century(self) -> Self:
        return self.start_of_century().add_years(100).sub_microseconds(1)

    # --- comparisons ---------------------------------------------------------

    def eq(self, other: datetime | date) -> bool:
        return self == _as_chrono(other)

    def ne(self, other: datetime | date) -> bool:
        return not self.eq(other)

    def gt(self, other: datetime | date) -> bool:
        return self > _as_chrono(other)

    def gte(self, other: datetime | date) -> bool:
        return self >= _as_chrono(other)

    def lt(self, other: datetime | date) -> bool:
        return self < _as_chrono(other)

    def lte(self, other: datetime | date) -> bool:
        return self <= _as_chrono(other)

    def equal_to(self, other: datetime | date) -> bool:
        return self.eq(other)

    def not_equal_to(self, other: datetime | date) -> bool:
        return self.ne(other)

    def greater_than(self, other: datetime | date) -> bool:
        return self.gt(other)

    def greater_than_or_equal_to(self, other: datetime | date) -> bool:
        return self.gte(other)

    def less_than(self, other: datetime | date) -> bool:
        return self.lt(other)

    def less_than_or_equal_to(self, other: datetime | date) -> bool:
        return self.lte(other)

    def between(
        self,
        first: datetime | date,
        second: datetime | date,
        *,
        equal: bool = True,
    ) -> bool:
        a, b = _as_chrono(first), _as_chrono(second)
        low, high = (a, b) if a <= b else (b, a)
        if equal:
            return low <= self <= high
        return low < self < high

    def is_weekday(self) -> bool:
        return self.weekday() < 5

    def is_weekend(self) -> bool:
        return self.weekday() >= 5

    def is_today(self) -> bool:
        return self.start_of_day() == type(self).today(self.tzinfo).start_of_day()

    def is_tomorrow(self) -> bool:
        return self.start_of_day() == type(self).tomorrow(self.tzinfo).start_of_day()

    def is_yesterday(self) -> bool:
        return self.start_of_day() == type(self).yesterday(self.tzinfo).start_of_day()

    def is_future(self) -> bool:
        return self > type(self).now(self.tzinfo)

    def is_past(self) -> bool:
        return self < type(self).now(self.tzinfo)

    def is_same_day(self, other: datetime | date) -> bool:
        other_c = _as_chrono(other)
        return (self.year, self.month, self.day) == (other_c.year, other_c.month, other_c.day)

    def is_same_month(self, other: datetime | date) -> bool:
        other_c = _as_chrono(other)
        return (self.year, self.month) == (other_c.year, other_c.month)

    def is_same_year(self, other: datetime | date) -> bool:
        return self.year == _as_chrono(other).year

    # --- diffs ---------------------------------------------------------------

    def diff(self, other: datetime | date | None = None) -> timedelta:
        other_c = _as_chrono(other) if other is not None else type(self).now(self.tzinfo)
        return self - other_c

    def diff_in_seconds(self, other: datetime | date | None = None, *, absolute: bool = True) -> float:
        delta = self.diff(other).total_seconds()
        return abs(delta) if absolute else delta

    def diff_in_minutes(self, other: datetime | date | None = None, *, absolute: bool = True) -> float:
        return self.diff_in_seconds(other, absolute=absolute) / 60

    def diff_in_hours(self, other: datetime | date | None = None, *, absolute: bool = True) -> float:
        return self.diff_in_seconds(other, absolute=absolute) / 3600

    def diff_in_days(self, other: datetime | date | None = None, *, absolute: bool = True) -> float:
        return self.diff_in_seconds(other, absolute=absolute) / 86400

    def diff_for_humans(
        self,
        other: datetime | date | None = None,
        *,
        absolute: bool = False,
    ) -> str:
        """Short English relative string (``3 hours ago``, ``in 2 days``)."""
        other_c = _as_chrono(other) if other is not None else type(self).now(self.tzinfo)
        seconds = (self - other_c).total_seconds()
        past = seconds < 0
        seconds = abs(seconds)
        if seconds < 1:
            return "just now"
        steps: list[tuple[str, float]] = [
            ("year", 365.25 * 86400),
            ("month", 30.4375 * 86400),
            ("week", 7 * 86400),
            ("day", 86400),
            ("hour", 3600),
            ("minute", 60),
            ("second", 1),
        ]
        for label, size in steps:
            if seconds >= size or label == "second":
                count = int(seconds // size) or 1
                unit = label if count == 1 else f"{label}s"
                phrase = f"{count} {unit}"
                if absolute:
                    return phrase
                return f"{phrase} ago" if past else f"in {phrase}"
        return "just now"  # pragma: no cover

    # --- formatting ----------------------------------------------------------

    def to_date_string(self) -> str:
        return self.strftime("%Y-%m-%d")

    def to_time_string(self) -> str:
        return self.strftime("%H:%M:%S")

    def to_datetime_string(self) -> str:
        return self.strftime("%Y-%m-%d %H:%M:%S")

    def to_iso_string(self) -> str:
        return self.isoformat()

    def to_atom_string(self) -> str:
        return self.strftime("%Y-%m-%dT%H:%M:%S%z")

    def format(self, fmt: str) -> str:
        return self.strftime(fmt)

    def __repr__(self) -> str:
        return (
            f"Chrono({self.year}, {self.month}, {self.day}, {self.hour}, "
            f"{self.minute}, {self.second}, {self.microsecond}, tzinfo={self.tzinfo!r})"
        )


def _resolve_tz(tz: tzinfo | str | None) -> tzinfo:
    if tz is None:
        return UTC
    if isinstance(tz, str):
        if tz.upper() in {"UTC", "Z"}:
            return UTC
        return ZoneInfo(tz)
    return tz


def _as_chrono(value: datetime | date | Chrono) -> Chrono:
    return Chrono.instance(value)


def _try_relative(text: str, tz: tzinfo | str | None) -> Chrono | None:
    """Tiny relative parser: ``+3 days``, ``-2 hours``, ``next monday`` (best-effort)."""
    match = re.fullmatch(
        r"([+-]?\d+)\s*(years?|months?|weeks?|days?|hours?|minutes?|seconds?)",
        text,
        flags=re.I,
    )
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower().rstrip("s") + "s"
        return Chrono.now(tz).add(**{unit: amount})
    return None
