"""M1 smoke tests — Application bootstrap in a scaffolded app. See docs/SMOKE.md."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from almasix.config import config
from almasix.framework import Application
from almasix.installer.cli import app as almasix_app
from almasix.installer.scaffold import scaffold_app
from tests.support import purge_generated_app_modules

pytestmark = [pytest.mark.smoke, pytest.mark.regression]

runner = CliRunner()


def test_m1_s1_scaffold_bootstraps_kernel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = runner.invoke(almasix_app, ["new", "kernel_smoke", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.stdout
    root = tmp_path / "kernel_smoke"
    purge_generated_app_modules()
    monkeypatch.chdir(root)
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.delenv("APP_NAME", raising=False)

    try:
        app = Application(root).bootstrap()
        assert app.is_booted
        assert config("app.name") == "KernelSmoke"
        assert app.path("config", "app.py").is_file()
    finally:
        purge_generated_app_modules()


def test_m1_s2_welcome_uses_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = scaffold_app("config_smoke", destination=tmp_path / "config_smoke")
    purge_generated_app_modules()
    monkeypatch.chdir(root)
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.delenv("APP_NAME", raising=False)
    try:
        module = importlib.import_module("bootstrap.app")
        assert module.application.is_bootstrapped
        client = TestClient(module.asgi)
        response = client.get("/")
        assert response.status_code == 200
        assert "Build something remarkable" in response.text
        # Web page and API both read app.name from config.
        assert "ConfigSmoke" in response.text
        assert client.get("/api/health").json()["app"] == "ConfigSmoke"
    finally:
        purge_generated_app_modules()
