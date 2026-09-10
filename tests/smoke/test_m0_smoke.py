"""M0 end-to-end smoke tests — see docs/SMOKE.md."""

from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from almasix.console.commands.runtime import DEFAULT_ASGI
from almasix.installer.cli import app as almasix_app
from almasix.installer.scaffold import scaffold_app
from almasix.smith.cli import app as smith_app
from tests.support import purge_generated_app_modules

pytestmark = [pytest.mark.smoke, pytest.mark.regression]

runner = CliRunner()


def test_s1_almasix_version() -> None:
    result = runner.invoke(almasix_app, ["version"])
    assert result.exit_code == 0
    assert "Almasix 0.5.1" in result.stdout


def test_s2_almasix_new_tree(tmp_path: Path) -> None:
    result = runner.invoke(almasix_app, ["new", "smoke_app", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.stdout
    root = tmp_path / "smoke_app"
    assert (root / "smith").is_file()
    assert (root / "bootstrap" / "app.py").is_file()
    assert (root / "app" / "http" / "controllers" / "welcome_controller.py").is_file()
    assert (root / "routes" / "api.py").is_file()
    assert (root / ".env.example").is_file()


def test_s3_almasix_new_rejects_bad_name(tmp_path: Path) -> None:
    result = runner.invoke(almasix_app, ["new", "9bad", "--path", str(tmp_path)])
    assert result.exit_code == 1


def test_s4_welcome_http(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = scaffold_app("http_smoke", destination=tmp_path / "http_smoke")
    purge_generated_app_modules()
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.chdir(root)
    monkeypatch.delenv("APP_NAME", raising=False)
    try:
        module = importlib.import_module("bootstrap.app")
        client = TestClient(module.asgi)
        response = client.get("/")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "Build something remarkable" in response.text
        assert module.asgi.title == "HttpSmoke"
    finally:
        purge_generated_app_modules()


def test_s5_smith_version() -> None:
    result = runner.invoke(smith_app, ["version"])
    assert result.exit_code == 0
    assert "Almasix 0.5.1" in result.stdout


def test_s6_smith_serve_without_bootstrap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(smith_app, ["serve"])
    assert result.exit_code == 1
    assert "bootstrap/app.py" in result.stderr


def test_s7_smith_serve_invokes_uvicorn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = scaffold_app("serve_smoke", destination=tmp_path / "serve_smoke")
    monkeypatch.chdir(root)
    mock_run = MagicMock()
    monkeypatch.setattr("almasix.console.commands.runtime.uvicorn.run", mock_run)

    result = runner.invoke(smith_app, ["serve", "--host", "127.0.0.1", "--port", "3010"])
    assert result.exit_code == 0, result.stdout
    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert args[0] == DEFAULT_ASGI
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 3010
