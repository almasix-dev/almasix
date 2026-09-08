"""M21 smoke — Processes docs, progress command, board."""

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


def test_m21_docs_and_sidebar_exist() -> None:
    assert (ROOT / "website" / "src" / "content" / "docs" / "processes.md").is_file()
    sidebar = (ROOT / "website" / "astro.config.mjs").read_text(encoding="utf-8")
    assert "processes" in sidebar


def test_m21_progress_process_command(progress_cwd: Path) -> None:
    del progress_cwd
    result = runner.invoke(smith_app, ["progress:process"])
    output = (result.stdout + result.stderr).lower()
    assert result.exit_code == 0, output
    assert "process demo ok" in output
    assert "pipe -> almasix pipes" in output


def test_m21_board_marks_processes_complete(progress_cwd: Path) -> None:
    del progress_cwd
    from app.http.controllers.progress_controller import _milestones

    m21 = next(m for m in _milestones() if m["id"] == "M21")
    assert m21["status"] == "complete"
    assert any("progress:process" in proof for proof in m21["proof"])
