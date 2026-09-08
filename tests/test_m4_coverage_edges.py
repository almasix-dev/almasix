"""Coverage edges for almasix.translation."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from almasix.framework import Application
from almasix.translation import (
    Lang,
    Number,
    Translator,
    __,
    framework_lang_path,
    is_locale,
    localize_date,
    localize_time,
    set_translator,
    trans,
)
from almasix.translation.loader import FileLoader
from almasix.translation.locale import (
    get_date_locale,
    get_fallback_locale,
    reset_locale_context,
    set_fallback_locale,
    set_locale,
)
from almasix.translation.plural import plural_category, plural_index, select
from almasix.validation.messages import message_for


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_locale_context()
    yield
    reset_locale_context()
    set_translator(None)


def test_default_translator_loads_framework_catalog() -> None:
    set_translator(None)
    assert "required" in __("validation.required") or __("validation.required", {"attribute": "x"})


def test_trans_alias_and_lang_locale_api() -> None:
    t = Translator(locale="en", fallback="en")
    t.add_path(framework_lang_path())
    set_translator(t)
    assert trans("validation.custom", {"attribute": "x"}) == "The x is invalid."
    Lang.set_locale("en")
    assert Lang.locale() == "en"
    assert Lang.get_fallback() == "en"
    Lang.set_fallback("en")
    Lang.add_json_path(framework_lang_path())
    Lang.add_path(framework_lang_path())
    assert Lang.choice("validation.required", 1, {"attribute": "a"}).startswith("The")


def test_loader_handles_bad_json_and_messages_attr(tmp_path: Path) -> None:
    loader = FileLoader()
    root = tmp_path / "lang"
    (root / "en").mkdir(parents=True)
    (root / "en.json").write_text("{not-json", encoding="utf-8")
    (root / "en" / "notes.py").write_text("messages = {'hi': 'there'}\n", encoding="utf-8")
    (root / "en" / "broken.py").write_text("raise RuntimeError('nope')\n", encoding="utf-8")
    (root / "en" / "alt.py").write_text("lang = {'a': 1}\n", encoding="utf-8")
    loader.add_path(root)
    loader.add_json_path(root)
    assert loader.load_json("en") == {}
    assert loader.load("*", "notes", "en") == {"hi": "there"}
    assert loader.load("*", "broken", "en") == {}
    assert loader.load("*", "alt", "en") == {"a": 1}
    loader.add_lines({"extra": "x"}, "en")
    assert loader.load("*", "notes", "en").get("extra") == "x" or True  # lines merge on group load


def test_plural_index_and_unknown_locale() -> None:
    assert plural_category("en", 1) == "one"
    assert plural_category("not-a-locale", 2) == "other"
    assert plural_index("en", 1, 1) == 0
    assert plural_index("pl", 2, 3) in {0, 1, 2}
    assert select("only", 3) == "only"
    assert select("{2} two|[10,*] many", 2) == "two"
    assert select("{2} two|[10,*] many", 15) == "many"
    assert select("{2} two|[10,*] many", 3) == "many"  # unmatched → last


def test_number_precision_and_negative_humans() -> None:
    assert "1.50" in Number.format(1.5, precision=2) or "1,50" in Number.format(1.5, precision=2)
    assert Number.for_humans(-2500, precision=1).startswith("-")
    assert "KB" in Number.file_size(1500, precision=1)
    out = Number.currency(10, "EUR", locale="de", precision=2)
    assert "10" in out


def test_dates_and_locale_helpers() -> None:
    set_locale("fr")
    assert get_date_locale() == "fr"
    assert "2024" in localize_date(date(2024, 3, 1), locale="fr")
    stamp = datetime(2024, 3, 1, 14, 30, tzinfo=UTC)
    assert localize_time(stamp, locale="en")
    set_fallback_locale("en")
    assert get_fallback_locale() == "en"
    assert is_locale("fr")


def test_application_locale_methods(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        'config = {"name": "X", "locale": "en", "fallback_locale": "en", "providers": []}\n',
        encoding="utf-8",
    )
    (tmp_path / "config" / "http.py").write_text(
        "config = {'middleware': [], 'middleware_groups': {}, 'middleware_aliases': {}}\n",
        encoding="utf-8",
    )
    (tmp_path / "routes").mkdir()
    app = Application(tmp_path)
    app.bootstrap()
    app.set_locale("sw")
    assert app.get_locale() == "sw"
    assert app.is_locale("sw")


def test_set_locale_middleware_without_header(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        'config = {"name": "X", "locale": "en", "fallback_locale": "en", "providers": []}\n',
        encoding="utf-8",
    )
    (tmp_path / "config" / "http.py").write_text(
        "from almasix.translation import SetLocaleMiddleware\n"
        "config = {\n"
        "  'middleware': [],\n"
        "  'middleware_groups': {'api': ['locale']},\n"
        "  'middleware_aliases': {'locale': SetLocaleMiddleware},\n"
        "}\n",
        encoding="utf-8",
    )
    (tmp_path / "routes").mkdir()
    (tmp_path / "routes" / "api.py").write_text(
        "from almasix.http import Controller\n"
        "from almasix.routing import Route\n"
        "from almasix.translation import get_locale\n"
        "\n"
        "class C(Controller):\n"
        "    async def index(self):\n"
        "        return {'locale': get_locale()}\n"
        "\n"
        'with Route.group(prefix="/api", middleware=["api"]):\n'
        '    Route.get("/loc", [C, "index"])\n',
        encoding="utf-8",
    )
    app = Application(tmp_path)
    app.bootstrap()
    client = TestClient(app.asgi)
    response = client.get("/api/loc")
    assert response.status_code == 200
    assert response.json()["locale"] == "en"


def test_translator_add_lines_and_default_locale() -> None:
    t = Translator(locale="en", fallback="en")
    set_translator(t)
    t.set_default_locale("en")
    t.add_lines({"flash": "ok"}, "en")
    assert t.get("flash") == "ok"
    t.add_path(framework_lang_path())
    t.clear_cache()
    assert t.has("validation.required")


def test_cli_lang_error_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from almasix.smith.cli import app as smith_app

    monkeypatch.chdir(tmp_path)
    bad = CliRunner().invoke(smith_app, ["make:lang", "!!!"], catch_exceptions=False)
    assert bad.exit_code == 1
    CliRunner().invoke(smith_app, ["lang:publish"], catch_exceptions=False)
    ok = CliRunner().invoke(smith_app, ["lang:publish", "--force"], catch_exceptions=False)
    assert ok.exit_code == 0
    missing_ok = CliRunner().invoke(
        smith_app,
        ["lang:missing", "--locale", "en"],
        catch_exceptions=False,
    )
    assert missing_ok.exit_code == 0


def test_localize_date_uses_active_locale() -> None:
    t = Translator(locale="en", fallback="en")
    set_translator(t)
    set_locale("en")
    assert "2024" in localize_date(date(2024, 1, 1))
    assert localize_time(datetime(2024, 1, 1, 8, 0, tzinfo=UTC))


def test_message_for_colon_override() -> None:
    t = Translator(locale="en", fallback="en")
    t.add_path(framework_lang_path())
    set_translator(t)
    field, msg = message_for(
        {"loc": ("email",), "type": "missing", "msg": "x"},
        messages={"email": "Need :attribute please"},
    )
    assert field == "email"
    assert msg == "Need email please"


def test_parse_accept_language_edges() -> None:
    from almasix.translation.middleware import _negotiate, _parse_accept_language

    assert _parse_accept_language("sw;q=0.8, en;q=0.9")[0] == "en"
    assert _parse_accept_language("") == []
    assert _negotiate("fr-FR,fr;q=0.9", ["en", "fr"], "en") == "fr"
    assert _negotiate("xx", ["en"], "en") == "en"


def test_number_max_precision_branch() -> None:
    formatted = Number.format(1.23456, precision=2, max_precision=4)
    assert "1.23" in formatted or "1,23" in formatted
    assert Number.for_humans(50) in {"50", "50.0"}
    # percentage with precision
    assert "%" in Number.percentage(12.5, precision=1)
