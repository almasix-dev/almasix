"""Laravel-shaped ``Number`` helpers."""

from __future__ import annotations

from typing import Any

# Irregular ordinal words; the rest are formed by suffix rules.
_ORDINAL_WORDS = {
    "one": "first",
    "two": "second",
    "three": "third",
    "five": "fifth",
    "eight": "eighth",
    "nine": "ninth",
    "twelve": "twelfth",
}

_default_locale = "en"
_default_currency = "USD"


class Number:
    """Numeric formatting helpers (Laravel ``Illuminate\\Support\\Number``)."""

    @classmethod
    def use_locale(cls, locale: str) -> None:
        global _default_locale
        _default_locale = locale

    @classmethod
    def default_locale(cls) -> str:
        return _default_locale

    @classmethod
    def use_currency(cls, currency: str) -> None:
        global _default_currency
        _default_currency = currency

    @classmethod
    def default_currency(cls) -> str:
        return _default_currency

    @classmethod
    def with_locale(cls, locale: str, callback: Any) -> Any:
        previous = cls.default_locale()
        cls.use_locale(locale)
        try:
            return callback()
        finally:
            cls.use_locale(previous)

    @classmethod
    def with_currency(cls, currency: str, callback: Any) -> Any:
        previous = cls.default_currency()
        cls.use_currency(currency)
        try:
            return callback()
        finally:
            cls.use_currency(previous)

    @staticmethod
    def format(
        number: float | int,
        *,
        precision: int | None = None,
        max_precision: int | None = None,
        locale: str | None = None,
    ) -> str:
        del locale
        if precision is not None:
            return f"{float(number):,.{precision}f}"
        if max_precision is not None:
            formatted = f"{float(number):,.{max_precision}f}".rstrip("0").rstrip(".")
            return formatted
        if isinstance(number, int) or float(number).is_integer():
            return f"{int(number):,}"
        return f"{float(number):,}"

    @staticmethod
    def percentage(
        number: float | int,
        *,
        precision: int = 0,
        max_precision: int | None = None,
        locale: str | None = None,
    ) -> str:
        del locale, max_precision
        return f"{float(number):.{precision}f}%"

    @staticmethod
    def currency(
        number: float | int,
        *,
        in_: str | None = None,
        locale: str | None = None,
        precision: int = 2,
    ) -> str:
        del locale
        code = in_ or Number.default_currency()
        symbol = {"USD": "$", "EUR": "€", "GBP": "£"}.get(code.upper(), f"{code} ")
        return f"{symbol}{float(number):,.{precision}f}"

    @staticmethod
    def file_size(bytes_: int | float, *, precision: int = 0) -> str:
        units = ["B", "KB", "MB", "GB", "TB", "PB"]
        size = float(bytes_)
        unit_index = 0
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1
        if precision == 0 and unit_index == 0:
            return f"{int(size)} {units[unit_index]}"
        return f"{size:.{precision}f} {units[unit_index]}"

    @staticmethod
    def abbreviate(number: float | int, *, precision: int = 0) -> str:
        units = ["", "K", "M", "B", "T"]
        value = float(number)
        unit_index = 0
        while abs(value) >= 1000 and unit_index < len(units) - 1:
            value /= 1000
            unit_index += 1
        if precision == 0:
            return f"{int(value)}{units[unit_index]}"
        return f"{value:.{precision}f}{units[unit_index]}"

    @staticmethod
    def clamp(number: float | int, min_value: float | int, max_value: float | int) -> float | int:
        return max(min_value, min(max_value, number))

    @staticmethod
    def ordinal(number: int) -> str:
        n = abs(int(number))
        if 10 <= (n % 100) <= 20:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{number}{suffix}"

    @staticmethod
    def pairs(total: int, chunk: int) -> list[tuple[int, int]]:
        result: list[tuple[int, int]] = []
        start = 1
        while start <= total:
            end = min(start + chunk - 1, total)
            result.append((start, end))
            start = end + 1
        return result

    @staticmethod
    def spell(number: int | float, *, locale: str | None = None) -> str:
        del locale
        # Minimal English spell-out for integers 0–999 (enough for DX demos).
        n = int(number)
        if n < 0:
            return "minus " + Number.spell(-n)
        ones = [
            "zero",
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "nine",
            "ten",
            "eleven",
            "twelve",
            "thirteen",
            "fourteen",
            "fifteen",
            "sixteen",
            "seventeen",
            "eighteen",
            "nineteen",
        ]
        tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
        if n < 20:
            return ones[n]
        if n < 100:
            return tens[n // 10] + (("-" + ones[n % 10]) if n % 10 else "")
        if n < 1000:
            rest = n % 100
            return ones[n // 100] + " hundred" + ((" " + Number.spell(rest)) if rest else "")
        return str(n)

    @staticmethod
    def spell_ordinal(number: int, *, locale: str | None = None) -> str:
        """Spell a number as an ordinal word: ``1`` becomes ``first``."""
        del locale
        spelled = Number.spell(int(number))
        head, _, last = spelled.rpartition("-")
        word = _ORDINAL_WORDS.get(last)
        if word is None:
            word = f"{last[:-1]}ieth" if last.endswith("y") else f"{last}th"
        return f"{head}-{word}" if head else word

    @staticmethod
    def parse_int(value: str, *, locale: str | None = None) -> int:
        """Read an integer out of a formatted string, discarding any fraction."""
        return int(Number.parse_float(value, locale=locale))

    @staticmethod
    def parse_float(value: str, *, locale: str | None = None) -> float:
        """Read a float out of a formatted string, ignoring grouping separators."""
        text = str(value).strip()
        if locale and locale.split("_")[0] in {"fr", "de", "es", "it", "pt", "nl", "tr", "ru"}:
            # These locales group with dots or spaces and use a comma decimal.
            text = text.replace(".", "").replace(" ", "").replace("\u00a0", "")
            text = text.replace(",", ".")
        else:
            text = text.replace(",", "").replace(" ", "")
        return float(text)

    @staticmethod
    def for_humans(number: float | int, *, precision: int = 0, abbreviate: bool = True) -> str:
        if abbreviate:
            return Number.abbreviate(number, precision=precision)
        return Number.format(number, precision=precision)

    @staticmethod
    def trim(number: float | int) -> float | int:
        value = float(number)
        if value.is_integer():
            return int(value)
        return value


# CamelCase aliases
Number.fileSize = Number.file_size  # type: ignore[attr-defined]
Number.forHumans = Number.for_humans  # type: ignore[attr-defined]
Number.useLocale = Number.use_locale  # type: ignore[attr-defined]
Number.defaultLocale = Number.default_locale  # type: ignore[attr-defined]
Number.useCurrency = Number.use_currency  # type: ignore[attr-defined]
Number.defaultCurrency = Number.default_currency  # type: ignore[attr-defined]
Number.withLocale = Number.with_locale  # type: ignore[attr-defined]
Number.withCurrency = Number.with_currency  # type: ignore[attr-defined]


Number.spellOrdinal = Number.spell_ordinal  # type: ignore[attr-defined]
Number.parseInt = Number.parse_int  # type: ignore[attr-defined]
Number.parseFloat = Number.parse_float  # type: ignore[attr-defined]
