"""M4 — Number helpers and date localization."""

from __future__ import annotations

from datetime import UTC, date, datetime

from almasix.translation import Number, localize_date, set_locale
from almasix.translation.locale import reset_locale_context


def setup_function() -> None:
    reset_locale_context()


def teardown_function() -> None:
    reset_locale_context()


def test_number_format_and_currency() -> None:
    set_locale("en")
    assert Number.format(1234.5) == "1,234.5"
    assert "$" in Number.currency(99.5, "USD")
    assert Number.percentage(10, precision=0) in {"10%", "10 %"}
    assert Number.file_size(2048, precision=0).endswith("KB")
    assert Number.for_humans(1_500_000, precision=1) in {"1.5M", "1,5M"}


def test_number_respects_locale() -> None:
    de = Number.format(1234.5, locale="de")
    assert "1.234" in de or "1,234" in de


def test_localize_date_follows_locale() -> None:
    value = date(2024, 1, 15)
    en = localize_date(value, format="medium", locale="en")
    de = localize_date(value, format="medium", locale="de")
    assert en != de or "2024" in en
    stamp = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
    assert "2024" in localize_date(stamp, locale="en")
