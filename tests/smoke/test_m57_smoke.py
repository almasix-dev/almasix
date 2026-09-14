"""M57 smoke — mail exhaust demo + board."""

from __future__ import annotations

import pathlib
import sys

import pytest
from typer.testing import CliRunner

from almasix.console.kernel import ConsoleKernel
from almasix.smith.cli import app as smith_app
from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke, pytest.mark.regression]

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROGRESS = ROOT / "examples" / "progress"


@pytest.fixture()
def progress_cwd(monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    kernel = ConsoleKernel.from_cwd(PROGRESS)
    kernel.load_console_routes()
    kernel.register_on_typer(smith_app)
    yield PROGRESS
    purge_generated_app_modules()
    while str(PROGRESS) in sys.path:
        sys.path.remove(str(PROGRESS))


def test_progress_mail_demo(progress_cwd: pathlib.Path) -> None:
    result = CliRunner().invoke(smith_app, ["progress:mail"])
    output = result.stdout + (result.stderr or "")
    assert result.exit_code == 0, output
    assert "failover → array" in output
    assert "mailgun → http fake" in output
    assert "on-demand → routed" in output
    assert "vonage → http fake" in output
    assert "slack → http fake" in output
    assert "mail demo ok" in output


def test_m57_board_marks_mail_complete(progress_cwd: pathlib.Path) -> None:
    import bootstrap.app as module
    from fastapi.testclient import TestClient

    client = TestClient(module.asgi, raise_server_exceptions=False)
    board = client.get("/api/progress").json()
    by_id = {m["id"]: m for m in board["milestones"]}
    assert by_id["M57"]["status"] == "complete"
    assert any("progress:mail" in p for p in by_id["M57"]["proof"])
    assert any("vonage" in p.lower() or "slack" in p.lower() for p in by_id["M57"]["proof"])
