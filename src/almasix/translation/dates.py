"""Date formatting that follows the active app locale."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from babel.dates import format_date, format_datetime, format_time


def _babel_locale(locale: str | None = None) -> str:
    if locale:
        return locale.replace("-", "_")
    from almasix.translation.helpers import get_translator

    return get_translator().get_locale().replace("-", "_")


def localize_date(
    value: date | datetime,
    format: str = "medium",
    locale: str | None = None,
) -> str:
    """Format a date/datetime using the active (or given) locale."""
    loc = _babel_locale(locale)
    if isinstance(value, datetime):
        return format_datetime(value, format=format, locale=loc)
    return format_date(value, format=format, locale=loc)


def localize_time(
    value: datetime,
    format: str = "medium",
    locale: str | None = None,
) -> str:
    return format_time(value, format=format, locale=_babel_locale(locale))


# Re-export Babel formatters for advanced use without inventing an API.
__all__ = ["format_date", "format_datetime", "format_time", "localize_date", "localize_time"]

# Silence unused-import style checkers that don't see re-exports.
_reexports: tuple[Any, ...] = (format_date, format_datetime, format_time)
