"""M4 smoke — dual-locale endpoint, scaffold lang tree, validation retrofit."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from almasix.installer.scaffold import scaffold_app
from almasix.smith.cli import app as smith_app
from almasix.validation.messages import message_for
from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke, pytest.mark.regression]

runner = CliRunner()


def test_m4_s1_scaffold_ships_lang_and_locale_config(tmp_path: Path) -> None:
    root = scaffold_app("m4_lang", destination=tmp_path / "m4_lang")
    assert (root / "lang" / "en" / "messages.py").is_file()
    env = (root / ".env").read_text(encoding="utf-8")
    assert "APP_LOCALE=en" in env
    assert "APP_FALLBACK_LOCALE=en" in env
    app_config = (root / "config" / "app.py").read_text(encoding="utf-8")
    assert 'env("APP_LOCALE"' in app_config


def test_m4_s2_lang_cli_in_scaffolded_app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = scaffold_app("m4_cli", destination=tmp_path / "m4_cli")
    monkeypatch.chdir(root)
    result = runner.invoke(smith_app, ["lang:publish", "--force"], catch_exceptions=False)
    assert result.exit_code == 0, result.stdout
    assert (root / "lang" / "en" / "validation.py").is_file()
    result = runner.invoke(smith_app, ["make:lang", "de"], catch_exceptions=False)
    assert result.exit_code == 0, result.stdout


def test_m4_s3_progress_locale_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(__file__).resolve().parents[2] / "examples" / "progress"
    purge_generated_app_modules()
    monkeypatch.chdir(root)
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.delenv("APP_NAME", raising=False)
    without_base_path(monkeypatch)
    try:
        module = importlib.import_module("bootstrap.app")
        client = TestClient(module.asgi)
        en = client.get("/api/locale", headers={"Accept-Language": "en"})
        assert en.status_code == 200
        body = en.json()
        assert body["locale"] == "en"
        assert "Welcome" in body["welcome"]
        assert body["items"] == "2 items"
        assert "I love Almasix." in body["json"]

        sw = client.get(
            "/api/locale",
            params={"count": 1, "name": "Ada"},
            headers={"Accept-Language": "sw"},
        )
        assert sw.status_code == 200
        sw_body = sw.json()
        assert sw_body["locale"] == "sw"
        assert "Karibu" in sw_body["welcome"]
        assert "Habari, Ada" in sw_body["hello"]
        assert "kimoja" in sw_body["items"].lower() or "Kitu" in sw_body["items"]
        assert "Napenda" in sw_body["json"]
    finally:
        purge_generated_app_modules()


def test_m4_s4_validation_messages_stay_byte_identical_for_en() -> None:
    field, msg = message_for({"loc": ("email",), "type": "missing", "msg": "Field required"})
    assert field == "email"
    assert msg == "The email field is required."
    _, msg = message_for(
        {
            "loc": ("name",),
            "type": "string_too_short",
            "msg": "x",
            "ctx": {"min_length": 3},
        }
    )
    assert msg == "The name must be at least 3 characters."
    _, msg = message_for(
        {
            "loc": ("tags",),
            "type": "too_short",
            "msg": "x",
            "ctx": {"min_length": 2},
        }
    )
    assert msg == "The tags must have at least 2 items."
