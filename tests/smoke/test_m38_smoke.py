"""M38 smoke — serve --workers, /up, deployment docs, version, demo, board."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from almasix.installer.scaffold import scaffold_app
from almasix.smith.cli import app as smith_app
from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke]

PROGRESS = Path(__file__).resolve().parents[2] / "examples" / "progress"
ROOT = Path(__file__).resolve().parents[2]
runner = CliRunner()


@pytest.fixture()
def progress_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    module = importlib.import_module("bootstrap.app")
    return TestClient(module.asgi)


def test_m38_package_version_is_040() -> None:
    from almasix import __version__

    assert __version__ == "0.6.2"
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.6.2"' in pyproject


def test_m38_serve_passes_workers_and_proxy_headers(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = scaffold_app("deploy_serve", destination=tmp_path / "deploy_serve")
    monkeypatch.chdir(root)
    monkeypatch.setattr(
        "almasix.console.commands.runtime.find_available_port",
        lambda host, start, end: start,
    )
    mock_run = MagicMock()
    monkeypatch.setattr("almasix.console.commands.runtime.uvicorn.run", mock_run)

    result = runner.invoke(
        smith_app,
        [
            "serve",
            "--port",
            "8000",
            "--workers",
            "3",
            "--proxy-headers",
            "--no-reload",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "3 workers" in result.stdout
    kwargs = mock_run.call_args.kwargs
    assert kwargs["workers"] == 3
    assert kwargs["reload"] is False
    assert kwargs["proxy_headers"] is True


def test_m38_scaffold_serves_health_up(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    root = scaffold_app("health_app", destination=tmp_path / "health_app")
    monkeypatch.chdir(root)
    monkeypatch.syspath_prepend(str(root))
    module = importlib.import_module("bootstrap.app")
    client = TestClient(module.asgi)
    response = client.get("/up")
    assert response.status_code == 200
    assert response.content == b""


def test_m38_deployment_docs_and_examples_exist() -> None:
    docs = (ROOT / "website" / "src" / "content" / "docs" / "deployment.md").read_text(
        encoding="utf-8"
    )
    assert "--workers" in docs
    assert "Trusted Publishing" in docs
    assert "examples/deploy" in docs

    sidebar = (ROOT / "website" / "astro.config.mjs").read_text(encoding="utf-8")
    assert "slug: 'deployment'" in sidebar

    deploy = ROOT / "examples" / "deploy"
    assert (deploy / "Dockerfile").is_file()
    assert (deploy / "docker-compose.yml").is_file()
    compose = (deploy / "docker-compose.yml").read_text(encoding="utf-8")
    assert "/up" in compose
    assert "queue:work" in compose

    publish = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
    assert "Trusted Publishing" in publish


def test_m38_demo_command_runs() -> None:
    result = subprocess.run(
        [sys.executable, "smith", "progress:deploy"],
        cwd=PROGRESS,
        capture_output=True,
        text=True,
        check=False,
    )
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    for line in (
        "smith serve --workers -> present",
        "optimize / view:cache -> ok",
        "GET /up -> 200",
        "docs/deployment.md -> present",
        "examples/deploy -> Dockerfile + compose",
        "publish.yml -> Trusted Publishing",
        "almasix.__version__ -> 0.6.2",
        "deployment + production ops ok",
    ):
        assert line in out, line


def test_m38_board_marks_deployment_complete(progress_client: TestClient) -> None:
    board = progress_client.get("/api/progress").json()
    by_id = {milestone["id"]: milestone for milestone in board["milestones"]}
    assert by_id["M38"]["status"] == "complete"
    assert "smith progress:deploy" in by_id["M38"]["proof"]
    assert any("--workers" in item for item in by_id["M38"]["proof"])
    assert any("/up" in item for item in by_id["M38"]["proof"])


def test_m38_readme_lists_deploy_demo() -> None:
    readme = (PROGRESS / "README.md").read_text(encoding="utf-8")
    assert "smith progress:deploy" in readme
    assert "**M38**" in readme
