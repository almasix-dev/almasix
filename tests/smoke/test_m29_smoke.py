"""M29 smoke — package development APIs, courier demo, docs, and the board."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from almasix.smith.cli import app as smith_app
from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke]

PROGRESS = Path(__file__).resolve().parents[2] / "examples" / "progress"
ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "website" / "src" / "content" / "docs"
COURIER = ROOT / "packages" / "courier"
runner = CliRunner()


@pytest.fixture()
def progress_cwd(monkeypatch: pytest.MonkeyPatch) -> Path:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    monkeypatch.syspath_prepend(str(COURIER / "src"))
    from almasix.console.kernel import ConsoleKernel

    ConsoleKernel.from_cwd(PROGRESS).register_on_typer(smith_app)
    return PROGRESS


@pytest.fixture()
def progress_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    monkeypatch.syspath_prepend(str(COURIER / "src"))
    module = importlib.import_module("bootstrap.app")
    app = module.application
    app._asgi = None
    module.asgi = app.asgi
    return TestClient(module.asgi, raise_server_exceptions=False)


def test_m29_progress_packages_command(progress_cwd: Path) -> None:
    result = runner.invoke(smith_app, ["progress:packages"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "packages ok" in result.stdout


def test_m29_courier_route(progress_client: TestClient) -> None:
    response = progress_client.get("/courier")
    assert response.status_code == 200
    assert response.json()["package"] == "courier"


def test_m29_board_marks_packages_complete(progress_client: TestClient) -> None:
    data = progress_client.get("/api/progress").json()
    by_id = {m["id"]: m for m in data["milestones"]}
    assert by_id["M29"]["status"] == "complete"
    assert by_id["M29"]["name"] == "Package development"
    assert any("progress:packages" in p for p in by_id["M29"]["proof"])


def test_m29_docs_and_sidebar_exist() -> None:
    assert (DOCS / "package-development.md").is_file()
    sidebar = (ROOT / "website" / "astro.config.mjs").read_text(encoding="utf-8")
    assert "package-development" in sidebar


def test_m29_courier_package_tree_exists() -> None:
    assert (COURIER / "src" / "courier" / "provider.py").is_file()
    assert "almasix.providers" in (COURIER / "pyproject.toml").read_text(encoding="utf-8")


def test_m29_make_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    from almasix.console.kernel import ConsoleKernel

    kernel = ConsoleKernel.for_cwd(tmp_path)
    kernel.discover_framework_commands()
    assert kernel.run_command("make:package", {"name": "billing"}, {}) == 0
    assert (tmp_path / "packages" / "billing" / "pyproject.toml").is_file()
    provider = (tmp_path / "packages" / "billing" / "src" / "billing" / "provider.py").read_text(
        encoding="utf-8"
    )
    assert "BillingServiceProvider" in provider
