"""M52 smoke — Sonar realtime demo + board proof."""

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


def test_m52_demo_command_runs() -> None:
    result = subprocess.run(
        [sys.executable, "smith", "progress:sonar"],
        cwd=PROGRESS,
        capture_output=True,
        text=True,
        check=False,
    )
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    for line in (
        "sonar   ->",
        "package -> @almasix/sonar",
        "https://www.npmjs.com/package/@almasix/sonar",
        "https://github.com/almasix-dev/sonar",
        "private ->",
        "sonar demo ok",
    ):
        assert line in out, line


def test_m52_board_marks_sonar_complete(progress_client: TestClient) -> None:
    board = progress_client.get("/api/progress").json()
    by_id = {m["id"]: m for m in board["milestones"]}
    assert by_id["M52"]["status"] == "complete"
    assert "smith progress:sonar" in by_id["M52"]["proof"]
    assert any("@almasix/sonar" in p for p in by_id["M52"]["proof"])
