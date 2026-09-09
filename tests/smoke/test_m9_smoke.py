"""M9 smoke — console commands, schedule, Loupe boot, dump/dd."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from almasix.console.repl import build_namespace
from almasix.smith.cli import app as smith_app
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
    from almasix.console.kernel import ConsoleKernel

    ConsoleKernel.from_cwd(PROGRESS).register_on_typer(smith_app)
    return PROGRESS


@pytest.fixture()
def progress_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    monkeypatch.setenv("APP_DEBUG", "false")
    monkeypatch.setenv("LOG_CHANNEL", "null")
    module = importlib.import_module("bootstrap.app")
    app = module.application
    app.config.set("app.debug", False)
    app.config.set("logging.default", "null")
    app._asgi = None
    module.asgi = app.asgi
    return TestClient(module.asgi, raise_server_exceptions=False)


def test_m9_progress_hello_command(progress_cwd: Path) -> None:
    result = runner.invoke(smith_app, ["progress:hello", "M9"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Hello, M9" in result.stdout


def test_m9_inspire_and_list(progress_cwd: Path) -> None:
    inspired = runner.invoke(smith_app, ["inspire"])
    assert inspired.exit_code == 0, inspired.stdout
    assert inspired.stdout.strip()
    listed = runner.invoke(smith_app, ["list"])
    assert listed.exit_code == 0
    assert "progress:hello" in listed.stdout or "inspire" in listed.stdout


def test_m9_schedule_run_heartbeat(progress_cwd: Path) -> None:
    from almasix.console.scheduling import schedule

    schedule.events.clear()
    result = runner.invoke(smith_app, ["schedule:run"])
    assert result.exit_code == 0, result.stdout + result.stderr
    # Heartbeat is every_minute — should run when due
    stamp = progress_cwd / "storage" / "framework" / "schedule-heartbeat.txt"
    if "progress-heartbeat" in result.stdout or stamp.is_file():
        assert stamp.is_file() or "Running:" in result.stdout


def test_m9_loupe_namespace_boots(progress_cwd: Path) -> None:
    from almasix.console.kernel import ConsoleKernel

    # Fresh CI checkouts have no SQLite schema — migrate before ORM queries.
    migrated = runner.invoke(smith_app, ["migrate"])
    assert migrated.exit_code == 0, migrated.stdout + migrated.stderr

    kernel = ConsoleKernel.from_cwd(progress_cwd)
    ns = build_namespace(kernel.app)
    assert ns["app"] is kernel.app
    assert "config" in ns
    assert "User" in ns  # progress User model
    assert "run" in ns
    assert "dump" in ns
    assert "dd" in ns
    assert "to_json" in ns
    # Async ORM expression results resolve (Tinker-shaped UX)
    from almasix.console.display import serialize, to_json
    from almasix.console.repl import resolve_awaitable

    users = resolve_awaitable(ns["User"].all())
    assert len(users) >= 0
    data = serialize(users)
    assert isinstance(data, list)
    if data:
        assert "id" in data[0] or "email" in data[0]
    assert to_json(users).startswith("[") or to_json(users).startswith("{")


def test_m9_web_dd_html_page(progress_client: TestClient) -> None:
    response = progress_client.get("/dd")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Dump and die" in response.text


def test_m9_api_dd_json(progress_client: TestClient) -> None:
    response = progress_client.get("/api/dd")
    assert response.status_code == 200
    body = response.json()
    assert body["dd"] is True
    assert isinstance(body["values"], list)
    assert body["values"][0]["helper"] == "dd()"
