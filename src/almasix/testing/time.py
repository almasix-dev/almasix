"""Moving the clock — Laravel's `travel`, `travelTo`, and `freezeTime`.

Freezing affects everything that asks the framework what time it is:
`almasix.support.now()`, `today()`, model timestamps, and the scheduler. Code
that calls `datetime.now()` itself is not fooled, and should not be.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from almasix.support.helpers import get_test_now, now, set_test_now


class TimeTraveller:
    """The handle `travel()` returns — a context manager, and a clock setter.

    `travel(days=1)` has already moved the clock by the time you hold this;
    using it as a context manager is how you say when to come back.
    """

    def __init__(self, moment: datetime, previous: datetime | None) -> None:
        self.moment = moment
        self.previous = previous

    def back(self) -> None:
        """Return to real time (or to wherever the clock was before)."""
        set_test_now(self.previous)

    def __enter__(self) -> datetime:
        return self.moment

    def __exit__(self, *_exception: object) -> None:
        self.back()

    def __repr__(self) -> str:
        return f"TimeTraveller({self.moment.isoformat()})"


def travel_to(moment: datetime) -> TimeTraveller:
    """Freeze the clock at this moment (Laravel `travelTo`)."""
    previous = get_test_now()
    at = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    set_test_now(at)
    return TimeTraveller(at, previous)


def travel(
    seconds: float = 0,
    *,
    minutes: float = 0,
    hours: float = 0,
    days: float = 0,
    weeks: float = 0,
) -> TimeTraveller:
    """Move the clock forward (or back, with a negative amount)."""
    delta = timedelta(seconds=seconds, minutes=minutes, hours=hours, days=days, weeks=weeks)
    return travel_to(now() + delta)


def freeze_time(callback: Callable[[datetime], Any] | None = None) -> Any:
    """Stop the clock where it is (Laravel `freezeTime`).

    With a callback, the clock is only frozen while it runs — which is how a
    test asserts on something that must happen "at the same instant".
    """
    traveller = travel_to(now())
    if callback is None:
        return traveller
    try:
        return callback(traveller.moment)
    finally:
        traveller.back()


def travel_back() -> None:
    """Real time again (Laravel `travelBack`)."""
    set_test_now(None)


@contextmanager
def frozen_time(moment: datetime | None = None) -> Iterator[datetime]:
    """`with frozen_time():` — the context-manager spelling of the above."""
    traveller = travel_to(moment or now())
    try:
        yield traveller.moment
    finally:
        traveller.back()
