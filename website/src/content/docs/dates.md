---
title: Dates (Chrono)
description: Fluent dates, timezones, diffs, and test time travel with almasix.chrono.
---

**Chrono** (`almasix.chrono`) is Almasix’s Carbon-class date library. It subclasses
Python’s `datetime`, so it works anywhere a datetime is accepted, and every
“mutating” method returns a **new** instance.

Helpers `now()` and `today()` return `Chrono`. Prefer Chrono in application code;
reach for raw `datetime` only when an external API demands it.

## Creating instances

```python
from almasix.chrono import Chrono

Chrono.now()
Chrono.utcnow()
Chrono.today()
Chrono.tomorrow()
Chrono.yesterday()
Chrono.parse("2024-06-15 14:30:00")
Chrono.parse("+3 days")
Chrono.create(2024, 6, 15, 14, 30, 0)
Chrono.create_from_format("%Y/%m/%d", "2024/06/15")
Chrono.fromtimestamp(1_700_000_000)
```

`parse` accepts ISO-8601 strings, a few relative phrases (`now`, `today`,
`+2 hours`), RFC 2822 timestamps, `datetime` / `date` objects, and unix
timestamps.

## Timezones

Chrono instances are timezone-aware (default UTC).

```python
from datetime import UTC

paris = Chrono.now("Europe/Paris")
utc = paris.utc()                 # same instant, UTC offset
wall = paris.timezone(UTC)        # keep wall-clock fields, change tz label
converted = paris.set_timezone("America/New_York")  # convert the instant
```

## Adding and subtracting

```python
moment = Chrono.parse("2024-01-31")

moment.add_days(1)
moment.sub_hours(3)
moment.add(weeks=2, hours=5)
moment.sub(months=1)
```

Month arithmetic clamps the day (Jan 31 + 1 month → Feb 29/28).

## Boundaries

```python
moment.start_of_day()
moment.end_of_month()
moment.start_of_week()      # Monday by default
moment.end_of_quarter()
moment.start_of_year()
```

Also: `start_of_hour` / `end_of_hour`, `start_of_minute` / `end_of_minute`,
`start_of_decade` / `end_of_decade`, `start_of_century` / `end_of_century`.

## Comparisons

```python
a = Chrono.parse("2024-06-01")
b = Chrono.parse("2024-06-02")

a.lt(b)          # True
a.between(a, b)  # True
a.is_weekend()
a.is_today()
b.is_future()
```

Aliases mirror Carbon where useful: `equal_to`, `greater_than_or_equal_to`, etc.

## Diffs

```python
a.diff_in_days(b)                 # 1.0
a.diff_for_humans(b)              # "1 day ago"
b.diff_for_humans(a)              # "in 1 day"
a.diff_for_humans(b, absolute=True)  # "1 day"
```

## Formatting

```python
moment.to_date_string()       # 2024-06-15
moment.to_time_string()       # 14:30:00
moment.to_datetime_string()   # 2024-06-15 14:30:00
moment.to_iso_string()
moment.format("%A, %d %B %Y")
```

## Helpers

```python
from almasix.support.helpers import now, today, set_test_now

now()      # Chrono
today()    # Chrono at 00:00:00
```

## Testing: freeze and travel

```python
from almasix.chrono import Chrono, freeze, travel_to, travel, return_time

travel_to("2020-01-01")
assert Chrono.now().year == 2020
travel(2, unit="days")
return_time()

with freeze("2021-05-05"):
    assert Chrono.today().year == 2021
# wall clock restored
```

`set_test_now` on both `Chrono` and the support helpers talks to the same clock,
so ORM code that calls `now()` freezes with your tests.

## Living example

```bash
cd examples/progress
python smith progress:dates
```
