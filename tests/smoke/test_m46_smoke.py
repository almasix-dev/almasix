"""M46 smoke — language server demo + board proof."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke, pytest.mark.regression]

PROGRESS = Path(__file__).resolve().parents[2] / "examples" / "progress"


@pytest.fixture()
def progress_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    module = importlib.import_module("bootstrap.app")
    return TestClient(module.asgi)


def test_m46_demo_command_runs() -> None:
    result = subprocess.run(
        [sys.executable, "smith", "progress:lsp"],
        cwd=PROGRESS,
        capture_output=True,
        text=True,
        check=False,
    )
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    for line in (
        "views  ->",
        "routes ->",
        "view-vars ->",
        "{{ app_name }} ->",
        "{{ url }} ->",
        "route('') ->",
        "ctrl+space ->",
        "@if ->",
        "env('APP_') ->",
        "DB.table('') ->",
        "user. ->",
        "quote-safe",
        "aligns under indent",
        "textDocument/formatting",
        "lsp ok",
    ):
        assert line in out, line


def test_m46_board_marks_lsp_complete(progress_client: TestClient) -> None:
    board = progress_client.get("/api/progress").json()
    by_id = {m["id"]: m for m in board["milestones"]}
    assert by_id["M46"]["status"] == "complete"
    assert "smith progress:lsp" in by_id["M46"]["proof"]
    assert any("Controller" in item for item in by_id["M46"]["proof"])
    assert any("app_name" in item for item in by_id["M46"]["proof"])
    assert any("route('')" in item for item in by_id["M46"]["proof"])
    assert any("env(" in item for item in by_id["M46"]["proof"])
    assert any("DB.table" in item for item in by_id["M46"]["proof"])
    assert any("user." in item or "attribute" in item.lower() for item in by_id["M46"]["proof"])
    assert any("@if" in item or "directive" in item.lower() for item in by_id["M46"]["proof"])
    assert any("formatting" in item.lower() or "format_prism" in item for item in by_id["M46"]["proof"])
