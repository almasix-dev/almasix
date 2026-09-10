"""M53 — Chrono coverage and behaviour."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from almasix.chrono import Chrono, freeze, return_time, set_test_now, travel, travel_to
from almasix.chrono.testing import _as_aware
from almasix.support.helpers import get_test_now, now, today
from almasix.support.helpers import set_test_now as helper_set_test_now


@pytest.fixture(autouse=True)
def _clear_clock() -> None:
    return_time()
    yield
    return_time()


def test_parse_and_create() -> None:
    c = Chrono.parse("2024-06-15T12:30:00+00:00")
    assert c.year == 2024 and c.month == 6 and c.day == 15
    assert Chrono.parse(c) is c or Chrono.parse(c) == c
    assert Chrono.parse(date(2024, 1, 2)).hour == 0
    assert Chrono.parse(1_700_000_000).year >= 2023
    created = Chrono.create(2020, 5, 4, 3, 2, 1, tz=UTC)
    assert created.to_datetime_string() == "2020-05-04 03:02:01"
    formatted = Chrono.create_from_format("%Y/%m/%d", "2022/03/04", tz=UTC)
    assert formatted.day == 4
    assert Chrono.parse("now").year == Chrono.now().year
    assert Chrono.parse("today").hour == 0
    assert Chrono.parse("tomorrow").is_tomorrow()
    assert Chrono.parse("yesterday").is_yesterday()
    assert Chrono.parse("+2 days").day == Chrono.now().add_days(2).day
    slash = Chrono.parse("2024/1/5 8:09:10")
    assert slash.month == 1 and slash.hour == 8
    with pytest.raises(ValueError):
        Chrono.parse("")
    with pytest.raises(ValueError):
        Chrono.parse("not-a-date")
    with pytest.raises(TypeError):
        Chrono.instance("nope")  # type: ignore[arg-type]


def test_add_sub_boundaries_and_format() -> None:
    c = Chrono(2024, 1, 31, 12, 30, 15, 123, UTC)
    assert c.add_months(1).day == 29 or c.add_months(1).month == 2  # leap
    assert c.add(days=1, hours=2).day == 1
    assert c.sub(seconds=15).second == 0
    assert c.add_years(1).year == 2025
    assert c.sub_years(1).year == 2023
    assert c.add_weeks(1).day == 7
    assert c.sub_weeks(1).day == 24
    assert c.add_minutes(30).minute == 0
    assert c.sub_minutes(30).minute == 0
    assert c.add_microseconds(1).microsecond == 124
    copied = c.copy()
    assert copied == c
    assert copied is not c
    assert c.clone() == c
    assert c.start_of_day().hour == 0
    assert c.end_of_day().hour == 23
    assert c.start_of_hour().minute == 0
    assert c.end_of_hour().minute == 59
    assert c.start_of_minute().second == 0
    assert c.end_of_minute().second == 59
    assert c.start_of_month().day == 1
    assert c.end_of_month().day == 31
    assert c.start_of_year().month == 1
    assert c.end_of_year().month == 12
    assert c.start_of_week().weekday() == 0
    assert c.end_of_week().weekday() == 6
    assert c.start_of_quarter().month == 1
    assert c.end_of_quarter().month == 3
    assert Chrono(2024, 5, 1, tzinfo=UTC).start_of_decade().year == 2020
    assert Chrono(2024, 5, 1, tzinfo=UTC).end_of_decade().year == 2029
    assert Chrono(2024, 5, 1, tzinfo=UTC).start_of_century().year == 2001
    assert Chrono(2024, 5, 1, tzinfo=UTC).end_of_century().year == 2100
    assert c.to_date_string() == "2024-01-31"
    assert c.to_time_string() == "12:30:15"
    assert "2024-01-31" in c.to_datetime_string()
    assert "T" in c.to_iso_string()
    assert c.format("%Y") == "2024"
    assert "Chrono(" in repr(c)
    with pytest.raises(ValueError):
        c.add(fortnights=1)  # type: ignore[arg-type]


def test_comparisons_and_diff() -> None:
    a = Chrono(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
    b = Chrono(2024, 6, 2, 12, 0, 0, tzinfo=UTC)
    assert a.lt(b) and a.lte(b) and b.gt(a) and b.gte(a)
    assert a.eq(a.copy()) and a.ne(b)
    assert a.equal_to(a) and a.not_equal_to(b)
    assert a.less_than(b) and a.less_than_or_equal_to(b)
    assert b.greater_than(a) and b.greater_than_or_equal_to(a)
    assert a.between(a, b) and a.between(a, b, equal=True)
    assert not a.between(a, b, equal=False)
    assert a.is_weekday() is False  # 2024-06-01 is Saturday
    assert a.is_weekend()
    assert Chrono(2024, 6, 3, tzinfo=UTC).is_weekday()
    assert Chrono(2024, 6, 2, tzinfo=UTC).is_weekend()  # Sunday
    assert a.is_same_day(Chrono(2024, 6, 1, 23, tzinfo=UTC))
    assert a.is_same_month(b)
    assert a.is_same_year(b)
    assert a.diff_in_days(b) == 1
    assert a.diff_in_hours(b) == 24
    assert a.diff_in_minutes(b) == 24 * 60
    assert a.diff_in_seconds(b) == 24 * 3600
    assert "day" in a.diff_for_humans(b, absolute=True)
    assert "ago" in a.diff_for_humans(b)
    assert "in" in b.diff_for_humans(a)
    assert Chrono.now().diff_for_humans(Chrono.now()) == "just now"


def test_timezone_helpers() -> None:
    c = Chrono(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    paris = c.set_timezone("Europe/Paris")
    assert paris.tzinfo is not None
    wall = c.timezone("America/New_York")
    assert wall.hour == 12
    assert c.utc().tzinfo == UTC
    assert Chrono.utcnow().tzinfo == UTC
    assert Chrono.now("UTC").tzinfo == UTC
    zoned = Chrono.now(ZoneInfo("UTC"))
    assert zoned.tzinfo is not None


def test_test_clock_and_helpers() -> None:
    travel_to("2020-01-15 10:00:00")
    assert Chrono.now().year == 2020
    assert Chrono.has_test_now()
    assert get_test_now() is not None
    moved = travel(2, unit="days")
    assert moved.day == 17
    travel(timedelta(hours=-1))
    assert Chrono.now().hour == 9
    with pytest.raises(ValueError):
        travel(1, unit="fortnights")
    return_time()
    with freeze("2021-03-03"):
        assert today().year == 2021
        assert now().month == 3
        assert Chrono.today().is_today()
        assert Chrono.tomorrow().is_tomorrow()
        assert Chrono.yesterday().is_yesterday()
        assert Chrono.now().add_days(1).is_future()
        assert Chrono.now().sub_days(1).is_past()
    assert Chrono.has_test_now() is False
    helper_set_test_now(Chrono(2018, 1, 1, tzinfo=UTC))
    assert now().year == 2018
    helper_set_test_now(None)
    set_test_now(datetime(2017, 2, 2, tzinfo=UTC))
    assert Chrono.now().year == 2017
    set_test_now(None)
    aware = _as_aware(datetime(2020, 1, 1))
    assert aware.tzinfo is not None
    assert _as_aware(Chrono.now()).year >= 2020


def test_fromtimestamp_and_email_parse() -> None:
    ts = Chrono.fromtimestamp(0, tz=UTC)
    assert ts.year == 1970
    # RFC 2822
    mail = Chrono.parse("Tue, 15 Nov 1994 08:12:31 GMT")
    assert mail.year == 1994


def test_add_timedelta_operators() -> None:
    c = Chrono(2024, 1, 1, tzinfo=UTC)
    assert (c + timedelta(days=1)).day == 2
    assert (c - timedelta(days=1)).year == 2023
    assert isinstance(c - Chrono(2023, 1, 1, tzinfo=UTC), timedelta)


def test_coverage_edges() -> None:
    same = Chrono(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert Chrono.instance(same) is same
    naive = datetime(2024, 1, 1, 12, 0, 0)
    assert Chrono.instance(naive).tzinfo == UTC
    assert Chrono.parse(same, tz="UTC").year == 2024
    assert Chrono.parse(datetime(2024, 1, 1, tzinfo=UTC), tz="UTC").year == 2024
    assert Chrono.create_from_format("%Y-%m-%d %H:%M:%S", "2024-01-02 03:04:05", tz="UTC").hour == 3
    stamped = Chrono.create_from_format("%Y-%m-%d %H:%M:%S%z", "2024-01-02 03:04:05+0000")
    assert Chrono.create_from_format("%Y-%m-%d %H:%M:%S%z", "2024-01-02 03:04:05+0000", tz="UTC").year == 2024
    assert stamped.year == 2024

    base = Chrono(2024, 1, 15, tzinfo=UTC)
    assert base.add_months(1.5).month in {2, 3}
    assert base.sub_months(1).month == 12
    assert base.add_seconds(1).second == 1
    assert base.sub_seconds(1).day == 14
    assert base.sub_microseconds(1).day == 14

    a = Chrono(2024, 6, 1, tzinfo=UTC)
    b = Chrono(2024, 6, 3, tzinfo=UTC)
    mid = Chrono(2024, 6, 2, tzinfo=UTC)
    assert a.ne(b) and mid.between(a, b, equal=False)
    assert a.gte(a) and a.lte(a)
    assert a.greater_than_or_equal_to(a)
    assert a.less_than_or_equal_to(a)
    assert a.not_equal_to(b)
    assert b.greater_than(a)
    assert a.less_than(b)
    assert a.equal_to(a.copy())

    assert a.diff_in_days(b, absolute=False) < 0
    assert "+" in a.to_atom_string() or a.to_atom_string().endswith("00")
    assert a.diff(b).total_seconds() < 0

    with freeze():
        assert Chrono.has_test_now()
    assert _as_aware("2020-01-01").year == 2020
    assert _as_aware(datetime(2020, 1, 1, tzinfo=UTC)).year == 2020
    assert _as_aware(datetime(2020, 1, 1)).tzinfo is not None

    assert Chrono.now("Z").tzinfo == UTC
    assert Chrono.parse("2024-01-01T00:00:00Z").tzinfo is not None
    assert Chrono.utcnow().tzinfo == UTC
    assert Chrono.instance(date(2024, 7, 4)).day == 4
    assert Chrono.parse("2024-01-01T12:00:00+00:00", tz="UTC").hour == 12
    assert Chrono(2024, 1, 1, 5, tzinfo=UTC).sub_hours(2).hour == 3
    assert Chrono(2024, 1, 1, 5, tzinfo=UTC).add_hours(2).hour == 7
