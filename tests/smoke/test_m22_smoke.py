"""M22 smoke — Concurrency docs, progress command, board, scaffold config."""

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


def test_m22_docs_and_sidebar_exist() -> None:
    assert (ROOT / "website" / "src" / "content" / "docs" / "concurrency.md").is_file()
    sidebar = (ROOT / "website" / "astro.config.mjs").read_text(encoding="utf-8")
    assert "concurrency" in sidebar


def test_m22_scaffolded_apps_get_a_concurrency_config(tmp_path: Path) -> None:
    from almasix.installer.scaffold import scaffold_app

    root = scaffold_app("concurrency_smoke", destination=tmp_path / "concurrency_smoke")
    config = root / "config" / "concurrency.py"
    assert config.is_file()
    assert "CONCURRENCY_DRIVER" in config.read_text(encoding="utf-8")


def test_m22_progress_concurrency_command(progress_cwd: Path) -> None:
    del progress_cwd
    result = runner.invoke(smith_app, ["progress:concurrency"])
    output = (result.stdout + result.stderr).lower()
    assert result.exit_code == 0, output
    assert "concurrency demo ok" in output
    assert "driver -> thread" in output


def test_m22_board_marks_concurrency_complete(progress_cwd: Path) -> None:
    del progress_cwd
    from app.http.controllers.progress_controller import _milestones

    m22 = next(m for m in _milestones() if m["id"] == "M22")
    assert m22["status"] == "complete"
    assert any("progress:concurrency" in proof for proof in m22["proof"])
