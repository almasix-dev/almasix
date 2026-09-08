"""M4 — smith lang:publish / make:lang / lang:missing."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from almasix.smith.cli import app as smith_app
from almasix.smith.lang_cmd import LangError, make_lang, missing_keys, publish_lang

runner = CliRunner()


def test_publish_and_make_lang(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    published = publish_lang(tmp_path)
    assert (published / "en" / "validation.py").is_file()
    assert (published / "en" / "auth.py").is_file()

    locale_path = make_lang("sw", tmp_path)
    assert (locale_path / "messages.py").is_file()
    assert (tmp_path / "lang" / "sw.json").is_file()

    with pytest.raises(LangError):
        make_lang("sw", tmp_path)

    with pytest.raises(LangError):
        make_lang("!!!", tmp_path)


def test_missing_keys_reports_gap(tmp_path: Path) -> None:
    publish_lang(tmp_path)
    make_lang("sw", tmp_path)
    # Fallback has validation keys; sw only has empty messages.
    gaps = missing_keys(tmp_path, locale="sw", fallback="en")
    assert any(key.startswith("validation.") for key in gaps)


def test_cli_lang_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(smith_app, ["lang:publish"], catch_exceptions=False)
    assert result.exit_code == 0, result.stdout
    result = runner.invoke(smith_app, ["make:lang", "fr"], catch_exceptions=False)
    assert result.exit_code == 0, result.stdout
    result = runner.invoke(
        smith_app,
        ["lang:missing", "--locale", "fr"],
        catch_exceptions=False,
    )
    assert result.exit_code == 1
    assert "validation." in result.stdout
