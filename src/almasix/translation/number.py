"""Locale-aware number helpers — mirrors Illuminate\\Support\\Number."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from babel.numbers import format_currency, format_decimal, format_percent

from almasix.translation.helpers import get_translator


def _babel_locale(locale: str | None = None) -> str:
    if locale:
        return locale.replace("-", "_")
    return get_translator().get_locale().replace("-", "_")


class Number:
    """Static helpers for locale-aware number formatting."""

    @staticmethod
    def format(
        number: float | Decimal,
        precision: int | None = None,
        max_precision: int | None = None,
        locale: str | None = None,
    ) -> str:
        kwargs: dict[str, Any] = {}
        if precision is not None:
            kwargs["decimal_quantization"] = False
            pattern = "#,##0." + ("0" * precision)
            if max_precision is not None and max_precision > precision:
                pattern += "#" * (max_precision - precision)
            return format_decimal(number, format=pattern, locale=_babel_locale(locale))
        return format_decimal(number, locale=_babel_locale(locale), **kwargs)

    @staticmethod
    def percentage(
        number: float | Decimal,
        precision: int = 0,
        max_precision: int | None = None,
        locale: str | None = None,
    ) -> str:
        del max_precision  # Babel percent pattern is driven by precision alone.
        # Laravel treats `number` as already a ratio fraction? Actually Laravel
        # Number::percentage(10) → "10%" (not 1000%). Pass through as percent value.
        value = float(number) / 100.0
        pattern = "#,##0" + (("." + ("0" * precision)) if precision else "") + "%"
        return format_percent(value, format=pattern, locale=_babel_locale(locale))

    @staticmethod
    def currency(
        number: float | Decimal,
        in_currency: str = "USD",
        locale: str | None = None,
        *,
        precision: int | None = None,
    ) -> str:
        kwargs: dict[str, Any] = {}
        if precision is not None:
            kwargs["format"] = f"¤#,##0.{'0' * precision}"
            kwargs["currency_digits"] = False
        return format_currency(
            number,
            in_currency,
            locale=_babel_locale(locale),
            **kwargs,
        )

    @staticmethod
    def file_size(bytes_value: float, precision: int = 0, locale: str | None = None) -> str:
        units = ["B", "KB", "MB", "GB", "TB", "PB"]
        value = float(bytes_value)
        unit_index = 0
        while value >= 1024 and unit_index < len(units) - 1:
            value /= 1024
            unit_index += 1
        formatted = Number.format(value, precision=precision, locale=locale)
        return f"{formatted} {units[unit_index]}"

    @staticmethod
    def for_humans(
        number: float | Decimal,
        precision: int = 0,
        max_precision: int | None = None,
        locale: str | None = None,
    ) -> str:
        del max_precision
        value = float(number)
        sign = "-" if value < 0 else ""
        value = abs(value)
        units = [
            (1_000_000_000_000, "T"),
            (1_000_000_000, "B"),
            (1_000_000, "M"),
            (1_000, "K"),
        ]
        for threshold, suffix in units:
            if value >= threshold:
                scaled = value / threshold
                return f"{sign}{Number.format(scaled, precision=precision, locale=locale)}{suffix}"
        return f"{sign}{Number.format(value, precision=precision, locale=locale)}"
