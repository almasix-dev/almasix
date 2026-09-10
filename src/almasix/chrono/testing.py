"""Test time travel — freeze, travel, and return the clock."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from almasix.chrono.chrono import Chrono


def set_test_now(moment: datetime | Chrono | None) -> None:
    """Freeze what ``Chrono.now()`` (and helpers ``now`` / ``today``) answer."""
    Chrono.set_test_now(moment)


def travel_to(moment: datetime | Chrono | str) -> Chrono:
    """Pin the test clock to ``moment`` and return it as ``Chrono``."""
    pinned = Chrono.parse(moment) if not isinstance(moment, Chrono) else moment
    Chrono.set_test_now(pinned)
    return Chrono.instance(pinned)


def travel(delta: timedelta | int | float, *, unit: str = "seconds") -> Chrono:
    """Move the test clock forward (or back with a negative delta).

    Pass a ``timedelta``, or a number plus ``unit`` (``seconds``, ``minutes``,
    ``hours``, ``days``, ``weeks``).
    """
    if isinstance(delta, timedelta):
        offset = delta
    else:
        amount = float(delta)
        key = unit.rstrip("s") + "s"
        if key not in {"seconds", "minutes", "hours", "days", "weeks"}:
            raise ValueError(f"Unsupported travel unit [{unit}].")
        offset = timedelta(**{key: amount})
    return travel_to(Chrono.now() + offset)


def return_time() -> None:
    """Clear the test clock so wall time is used again."""
    Chrono.set_test_now(None)


@contextmanager
def freeze(moment: datetime | Chrono | str | None = None) -> Iterator[Chrono]:
    """Context manager that freezes time for the block, then restores it."""
    previous = Chrono.get_test_now()
    try:
        if moment is None:
            pinned = Chrono.now()
            Chrono.set_test_now(pinned)
        else:
            pinned = travel_to(moment)
        yield Chrono.instance(pinned)
    finally:
        Chrono.set_test_now(previous)


# Keep a private alias used by older call sites during the M53 transition.
def _as_aware(moment: Any) -> datetime:
    if isinstance(moment, Chrono):
        return moment
    if isinstance(moment, datetime):
        return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    return Chrono.parse(moment)
