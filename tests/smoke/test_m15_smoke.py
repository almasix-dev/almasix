"""Smoke — Cache façade boots in progress; milestone board lists M15."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from avalon.grail.cli import app as grail_app
from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke, pytest.mark.regression]

PROGRESS = Path(__file__).resolve().parents[2] / "examples" / "progress"
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


@pytest.fixture()
def progress_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    module = importlib.import_module("bootstrap.app")
    app = module.application
    app._asgi = None  # noqa: SLF001
    module.asgi = app.asgi
    return TestClient(module.asgi, raise_server_exceptions=False)


def test_m15_progress_cache_command(progress_cwd: Path) -> None:
    result = runner.invoke(grail_app, ["progress:cache"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "cache demo ok" in result.stdout or "remember" in result.stdout.lower()


def test_m15_progress_board_marks_cache_complete(progress_client: TestClient) -> None:
    data = progress_client.get("/api/progress").json()
    by_id = {m["id"]: m for m in data["milestones"]}
    assert by_id["M14"]["status"] == "complete"
    assert by_id["M15"]["status"] == "complete"
    assert by_id["M15"]["name"] == "Cache"
    assert by_id["M16"]["status"] == "complete"
    assert by_id["M16"]["name"] == "Redis"
    assert by_id["M29"]["status"] == "planned"
    assert by_id["M29"]["name"] == "Package development"
    assert data["total"] == 30  # M0–M29
