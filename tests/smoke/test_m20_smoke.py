"""M20 smoke — HTTP Client docs, progress command, board."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from almasix.smith.cli import app as smith_app
from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke]

PROGRESS = Path(__file__).resolve().parents[2] / "examples" / "progress"
ROOT = Path(__file__).resolve().parents[2]
runner = CliRunner()


@pytest.fixture()
def progress_cwd(monkeypatch: pytest.MonkeyPatch) -> Path:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    from almasix.console.kernel import ConsoleKernel

    ConsoleKernel.from_cwd(PROGRESS).register_on_typer(smith_app)
    return PROGRESS


def test_m20_docs_and_sidebar_exist() -> None:
    assert (ROOT / "website" / "src" / "content" / "docs" / "http-client.md").is_file()
    sidebar = (ROOT / "website" / "astro.config.mjs").read_text(encoding="utf-8")
    assert "http-client" in sidebar


def test_m20_progress_http_command(progress_cwd: Path) -> None:
    del progress_cwd
    result = runner.invoke(smith_app, ["progress:http"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "http client demo ok" in (result.stdout + result.stderr).lower()


def test_m20_board_marks_http_client_complete(progress_cwd: Path) -> None:
    del progress_cwd
    from app.http.controllers.progress_controller import _milestones

    m20 = next(m for m in _milestones() if m["id"] == "M20")
    assert m20["status"] == "complete"
    m21 = next(m for m in _milestones() if m["id"] == "M21")
    assert m21["status"] in {"next", "planned"}
