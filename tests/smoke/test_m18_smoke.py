"""M18 smoke — Events docs, progress command, board."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from avalon.grail.cli import app as grail_app
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
    from avalon.console.kernel import ConsoleKernel

    ConsoleKernel.from_cwd(PROGRESS).register_on_typer(grail_app)
    return PROGRESS


def test_m18_docs_and_sidebar_exist() -> None:
    assert (ROOT / "website" / "src" / "content" / "docs" / "events.md").is_file()
    assert "events" in (ROOT / "website" / "astro.config.mjs").read_text(encoding="utf-8")


def test_m18_progress_events_command(progress_cwd: Path) -> None:
    del progress_cwd
    result = runner.invoke(grail_app, ["progress:events"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "events demo ok" in (result.stdout + result.stderr).lower()


def test_m18_board_marks_events_complete(progress_cwd: Path) -> None:
    del progress_cwd
    from app.http.controllers.progress_controller import _milestones

    m18 = next(m for m in _milestones() if m["id"] == "M18")
    assert m18["status"] == "complete"
    m19 = next(m for m in _milestones() if m["id"] == "M19")
    assert m19["status"] == "next"
