"""M17 smoke — Encryption docs scaffold, progress command, key:generate."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from avalon.grail.cli import app as grail_app
from avalon.installer.scaffold import scaffold_app
from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke]

PROGRESS = Path(__file__).resolve().parents[2] / "examples" / "progress"
runner = CliRunner()
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def progress_cwd(monkeypatch: pytest.MonkeyPatch) -> Path:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    from avalon.console.kernel import ConsoleKernel

    ConsoleKernel.from_cwd(PROGRESS).register_on_typer(grail_app)
    return PROGRESS


def test_m17_scaffold_ships_previous_keys(tmp_path: Path) -> None:
    root = scaffold_app("m17_enc", destination=tmp_path / "m17_enc")
    app_cfg = (root / "config" / "app.py").read_text(encoding="utf-8")
    assert "previous_keys" in app_cfg
    assert "APP_PREVIOUS_KEYS" in app_cfg or "APP_PREVIOUS_KEYS" in (
        root / ".env"
    ).read_text(encoding="utf-8")
    env = (root / ".env").read_text(encoding="utf-8")
    assert "APP_KEY=" in env
    assert "APP_PREVIOUS_KEYS" in env


def test_m17_docs_and_sidebar_exist() -> None:
    assert (ROOT / "website" / "src" / "content" / "docs" / "encryption.md").is_file()
    sidebar = (ROOT / "website" / "astro.config.mjs").read_text(encoding="utf-8")
    assert "encryption" in sidebar


def test_m17_progress_encryption_command(progress_cwd: Path) -> None:
    del progress_cwd
    result = runner.invoke(grail_app, ["progress:encryption"])
    assert result.exit_code == 0, result.stdout + result.stderr
    out = (result.stdout + result.stderr).lower()
    assert "encryption demo ok" in out
    assert "tamper" in out


def test_m17_board_marks_encryption_complete(progress_cwd: Path) -> None:
    del progress_cwd
    from app.http.controllers.progress_controller import _milestones

    m17 = next(m for m in _milestones() if m["id"] == "M17")
    assert m17["status"] == "complete"
    m18 = next(m for m in _milestones() if m["id"] == "M18")
    assert m18["status"] == "next"
