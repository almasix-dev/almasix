"""Laravel-shaped pluralization: pipe forms, intervals, and Babel CLDR."""

from __future__ import annotations

import re
from typing import Any

from babel import Locale
from babel.core import UnknownLocaleError

_SEGMENT_RE = re.compile(
    r"^\s*(?:\{(\d+)\}|\[(\d+),(\d+|\*)\])?\s*(.*)$",
    re.DOTALL,
)

# CLDR category order used when a string has one segment per category.
_CATEGORY_ORDER = ("zero", "one", "two", "few", "many", "other")


def select(line: str, number: float, locale: str = "en") -> str:
    """Pick the plural segment for `number` from a Laravel pipe string."""
    if "|" not in line:
        return line

    segments = _split_segments(line)
    # Interval / explicit-index segments take priority when present.
    for inline_number, start, end, text in segments:
        if inline_number is not None and inline_number == int(number):
            return text
        if start is not None and end is not None and _in_range(number, start, end):
            return text

    # Strip interval prefixes and select by CLDR index.
    texts = [text for _, _, _, text in segments]
    if any(s[0] is not None or s[1] is not None for s in segments):
        # Had intervals but none matched — fall through to last/"other".
        return texts[-1] if texts else line

    index = plural_index(locale, number, len(texts))
    if 0 <= index < len(texts):
        return texts[index]
    return texts[-1] if texts else line


def plural_index(locale: str, number: float, parts: int) -> int:
    """Map a count onto a segment index using Babel CLDR plural rules."""
    category = plural_category(locale, number)
    if parts <= 1:
        return 0
    if parts == 2:
        # English-style singular|plural → one|other.
        return 0 if category == "one" else 1

    try:
        babel_locale = Locale.parse(_babel_locale(locale))
        categories = list(babel_locale.plural_form.tags)  # type: ignore[attr-defined]
    except (UnknownLocaleError, ValueError, AttributeError):
        categories = list(_CATEGORY_ORDER)

    # Prefer the locale's declared tags; fall back to the full CLDR order.
    ordered = [c for c in _CATEGORY_ORDER if c in set(categories)] or list(_CATEGORY_ORDER)
    if category in ordered:
        index = ordered.index(category)
        return min(index, parts - 1)
    return parts - 1


def plural_category(locale: str, number: float) -> str:
    try:
        babel_locale = Locale.parse(_babel_locale(locale))
        return str(babel_locale.plural_form(number))
    except (UnknownLocaleError, ValueError):
        return "one" if number == 1 else "other"


def _babel_locale(locale: str) -> str:
    return locale.replace("-", "_")


def _split_segments(line: str) -> list[tuple[int | None, int | None, Any, str]]:
    parts = line.split("|")
    result: list[tuple[int | None, int | None, Any, str]] = []
    for part in parts:
        match = _SEGMENT_RE.match(part)
        if not match:  # pragma: no cover - pattern always matches via (.*)
            result.append((None, None, None, part))
            continue
        exact, start, end, text = match.groups()
        result.append(
            (
                int(exact) if exact is not None else None,
                int(start) if start is not None else None,
                end if end is not None else None,
                text,
            )
        )
    return result


def _in_range(number: float, start: int, end: str | int) -> bool:
    value = float(number)
    if end == "*":
        return value >= start
    return start <= value <= int(end)
