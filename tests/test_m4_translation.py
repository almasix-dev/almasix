"""M4 — Translator, plurals, placeholders, namespaces, locale scope."""

from __future__ import annotations

from pathlib import Path

import pytest

from almasix.translation import (
    Lang,
    Translator,
    __,
    framework_lang_path,
    get_locale,
    set_locale,
    set_translator,
    trans_choice,
)
from almasix.translation.locale import peek_locale, reset_locale_context
from almasix.translation.plural import select


@pytest.fixture(autouse=True)
def _clean_locale() -> None:
    reset_locale_context()
    yield
    reset_locale_context()


@pytest.fixture
def translator(tmp_path: Path) -> Translator:
    lang = tmp_path / "lang"
    (lang / "en").mkdir(parents=True)
    (lang / "sw").mkdir(parents=True)
    (lang / "en" / "messages.py").write_text(
        'translations = {"welcome": "Hello, :name", "title": "Welcome"}\n',
        encoding="utf-8",
    )
    (lang / "sw" / "messages.py").write_text(
        'translations = {"welcome": "Habari, :name"}\n',
        encoding="utf-8",
    )
    (lang / "en.json").write_text('{"I love Almasix.": "I love Almasix."}\n', encoding="utf-8")
    (lang / "sw.json").write_text('{"I love Almasix.": "Napenda Almasix."}\n', encoding="utf-8")
    t = Translator(locale="en", fallback="en")
    t.add_path(framework_lang_path())
    t.add_path(lang)
    t.add_json_path(lang)
    set_translator(t)
    return t


def test_file_and_json_lookup(translator: Translator) -> None:
    assert __("messages.title") == "Welcome"
    assert __("messages.welcome", {"name": "Ada"}) == "Hello, Ada"
    assert __("I love Almasix.") == "I love Almasix."
    set_locale("sw")
    assert __("messages.welcome", {"name": "Ada"}) == "Habari, Ada"
    assert __("I love Almasix.") == "Napenda Almasix."
    # Fallback for missing key in sw.
    assert __("messages.title") == "Welcome"


def test_placeholder_case_transforms(translator: Translator) -> None:
    assert translator.make_replacements(":name :Name :NAME", {"name": "ada"}) == "ada Ada ADA"


def test_plural_intervals_and_cldr() -> None:
    line = "{0} none|{1} one|[2,*] :count items"
    assert select(line, 0) == "none"
    assert select(line, 1) == "one"
    assert select(line, 7, "en") == ":count items"
    assert select("apple|apples", 1, "en") == "apple"
    assert select("apple|apples", 3, "en") == "apples"


def test_trans_choice_injects_count(translator: Translator) -> None:
    translator.add_lines(
        {"cart": "{0} empty|{1} one item|[2,*] :count items"},
        "en",
    )
    assert trans_choice("cart", 0) == "empty"
    assert trans_choice("cart", 1) == "one item"
    assert trans_choice("cart", 4) == "4 items"


def test_missing_key_returns_key_and_callback(translator: Translator) -> None:
    assert __("messages.missing") == "messages.missing"
    seen: list[str] = []

    def handler(key: str, locale: str, replace: dict) -> str | None:
        seen.append(key)
        return f"missing:{key}"

    Lang.handle_missing_keys_using(handler)
    assert __("nope.thing") == "missing:nope.thing"
    assert seen == ["nope.thing"]
    Lang.handle_missing_keys_using(None)


def test_namespaces_and_vendor_override(tmp_path: Path, translator: Translator) -> None:
    package = tmp_path / "pkg" / "lang"
    (package / "en").mkdir(parents=True)
    (package / "en" / "messages.py").write_text(
        'translations = {"pulse": "from package"}\n',
        encoding="utf-8",
    )
    Lang.add_namespace("acme", package)
    assert Lang.get("acme::messages.pulse") == "from package"

    vendor = tmp_path / "lang" / "vendor" / "acme" / "en"
    vendor.mkdir(parents=True)
    (vendor / "messages.py").write_text(
        'translations = {"pulse": "from vendor"}\n',
        encoding="utf-8",
    )
    # App lang path already registered; clear cache so vendor is seen.
    translator.clear_cache()
    assert Lang.get("acme::messages.pulse") == "from vendor"


def test_has_and_locale_helpers(translator: Translator) -> None:
    assert Lang.has("messages.title")
    assert not Lang.has_for_locale("messages.welcome", "xx")
    assert peek_locale() is None
    set_locale("sw")
    assert get_locale() == "sw"
    assert translator.get_locale() == "sw"


def test_framework_validation_catalog_loaded(translator: Translator) -> None:
    assert __("validation.required", {"attribute": "email"}) == ("The email field is required.")
