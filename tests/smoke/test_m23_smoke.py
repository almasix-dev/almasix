"""M23 smoke — API Resources docs, progress command, route, board."""

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
    module = importlib.import_module("bootstrap.app")
    return TestClient(module.asgi)


def test_m23_docs_and_sidebar_exist() -> None:
    assert (ROOT / "website" / "src" / "content" / "docs" / "api-resources.md").is_file()
    sidebar = (ROOT / "website" / "astro.config.mjs").read_text(encoding="utf-8")
    assert "api-resources" in sidebar


def test_m23_make_resource_generates_both_shapes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from almasix.installer.scaffold import scaffold_app

    root = scaffold_app("m23_make", destination=tmp_path / "m23_make")
    monkeypatch.chdir(root)

    assert runner.invoke(smith_app, ["make:resource", "PostResource"]).exit_code == 0
    single = root / "app" / "http" / "resources" / "post_resource.py"
    assert "JsonResource" in single.read_text(encoding="utf-8")

    assert runner.invoke(smith_app, ["make:resource", "PostCollection", "-c"]).exit_code == 0
    many = root / "app" / "http" / "resources" / "post_collection.py"
    assert "ResourceCollection" in many.read_text(encoding="utf-8")


def test_m23_progress_resources_command(progress_cwd: Path) -> None:
    del progress_cwd
    result = runner.invoke(smith_app, ["progress:resources"])
    output = result.stdout + result.stderr
    assert result.exit_code == 0, output
    assert "resources demo ok" in output
    assert "'data':" in output
    assert "current_page" in output


def test_m23_routes_return_resources(progress_client: TestClient) -> None:
    listing = progress_client.get("/api/resources")
    assert listing.status_code == 200
    payload = listing.json()
    assert payload["meta"]["current_page"] == 1
    assert payload["links"]["first"]
    assert payload["data"][0]["author"]["name"]

    single = progress_client.get("/api/resources/1")
    assert single.status_code == 200
    assert single.json()["data"]["id"] == 1
    assert progress_client.get("/api/resources/9999").status_code == 404


def test_m23_board_marks_resources_complete(progress_cwd: Path) -> None:
    del progress_cwd
    from app.http.controllers.progress_controller import _milestones

    m23 = next(m for m in _milestones() if m["id"] == "M23")
    assert m23["status"] == "complete"
    assert any("progress:resources" in proof for proof in m23["proof"])
