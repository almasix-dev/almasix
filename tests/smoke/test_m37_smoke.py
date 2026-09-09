"""M37 smoke — Signet PATs, board proof, csrf-cookie route."""

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


def test_m37_demo_command_runs() -> None:
    result = subprocess.run(
        [sys.executable, "smith", "progress:tokens"],
        cwd=PROGRESS,
        capture_output=True,
        text=True,
        check=False,
    )
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    for line in (
        "create_token ->",
        "GET /api/user (Bearer PAT) -> 200",
        "GET /signet/csrf-cookie -> 204",
        "signet tokens ok",
    ):
        assert line in out, line


def test_m37_board_marks_tokens_complete(progress_client: TestClient) -> None:
    board = progress_client.get("/api/progress").json()
    by_id = {milestone["id"]: milestone for milestone in board["milestones"]}
    assert by_id["M37"]["status"] == "complete"
    assert "smith progress:tokens" in by_id["M37"]["proof"]
    assert any("auth:signet" in item for item in by_id["M37"]["proof"])


def test_m37_csrf_cookie_route(progress_client: TestClient) -> None:
    response = progress_client.get("/signet/csrf-cookie")
    assert response.status_code == 204
