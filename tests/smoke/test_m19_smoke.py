"""M19 smoke — Authorization docs, progress command, board."""

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


def test_m19_docs_and_sidebar_exist() -> None:
    assert (ROOT / "website" / "src" / "content" / "docs" / "authorization.md").is_file()
    sidebar = (ROOT / "website" / "astro.config.mjs").read_text(encoding="utf-8")
    assert "authorization" in sidebar


def test_m19_progress_authorization_command(progress_cwd: Path) -> None:
    del progress_cwd
    result = runner.invoke(smith_app, ["progress:authorization"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "authorization demo ok" in (result.stdout + result.stderr).lower()


def test_m19_board_marks_authorization_complete(progress_cwd: Path) -> None:
    del progress_cwd
    from app.http.controllers.progress_controller import _milestones

    m19 = next(m for m in _milestones() if m["id"] == "M19")
    assert m19["status"] == "complete"
    m20 = next(m for m in _milestones() if m["id"] == "M20")
    assert m20["status"] == "complete"


def test_m19_scaffold_registers_can_alias(tmp_path: Path) -> None:
    from almasix.installer.scaffold import scaffold_app

    root = scaffold_app("m19_authz", destination=tmp_path / "m19_authz")
    boot = (root / "bootstrap" / "app.py").read_text(encoding="utf-8")
    assert '"can": Authorize' in boot or "'can': Authorize" in boot
