"""M47 smoke — editor integrations demo + board proof."""

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


def test_m47_demo_command_runs() -> None:
    result = subprocess.run(
        [sys.executable, "smith", "progress:ide"],
        cwd=PROGRESS,
        capture_output=True,
        text=True,
        check=False,
    )
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    for line in (
        "install ->",
        "stubs   ->",
        "ide-support -> https://github.com/almasix-dev/ide-support",
        "ide ok",
    ):
        assert line in out, line


def test_m47_board_marks_ide_complete(progress_client: TestClient) -> None:
    board = progress_client.get("/api/progress").json()
    by_id = {m["id"]: m for m in board["milestones"]}
    assert by_id["M47"]["status"] == "complete"
    assert "smith progress:ide" in by_id["M47"]["proof"]
    assert any("almasix-dev/ide-support" in p for p in by_id["M47"]["proof"])
