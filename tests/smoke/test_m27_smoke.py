"""M27 smoke — search docs, the commands, the route, the board."""

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


def test_m27_docs_and_sidebar_exist() -> None:
    page = ROOT / "website" / "src" / "content" / "docs" / "search.md"
    assert page.is_file()
    sidebar = (ROOT / "website" / "astro.config.mjs").read_text(encoding="utf-8")
    assert "'search'" in sidebar


def test_m27_a_scaffolded_app_can_search(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from almasix.installer.scaffold import scaffold_app

    root = scaffold_app("m27_scaffold", destination=tmp_path / "m27_scaffold")
    monkeypatch.chdir(root)
    config = (root / "config" / "scout.py").read_text(encoding="utf-8")
    assert '"driver": env("SCOUT_DRIVER", "database")' in config
    assert '"meilisearch"' in config


def test_m27_scout_status_reports_the_engine_and_the_models(progress_cwd: Path) -> None:
    del progress_cwd
    result = runner.invoke(smith_app, ["scout:status"])
    output = result.stdout + result.stderr
    assert result.exit_code == 0, output
    assert "searching via [database]" in output
    assert "Post -> posts" in output


def test_m27_scout_import_and_flush_run(progress_cwd: Path) -> None:
    del progress_cwd
    imported = runner.invoke(smith_app, ["scout:import", "Post"])
    assert imported.exit_code == 0, imported.stdout + imported.stderr
    assert "Post -> posts" in imported.stdout

    flushed = runner.invoke(smith_app, ["scout:flush", "Post"])
    assert flushed.exit_code == 0, flushed.stdout + flushed.stderr
    assert "flushed" in flushed.stdout


def test_m27_progress_search_command(progress_cwd: Path) -> None:
    del progress_cwd
    result = runner.invoke(smith_app, ["progress:search"])
    output = result.stdout + result.stderr
    assert result.exit_code == 0, output
    assert "search demo ok" in output
    assert "driver -> database [posts]" in output
    assert "search -> ['Notes on engines']" in output
    assert "collection -> ['Notes on engines'] filtered in Python" in output
    assert "index -> 2 published post(s)" in output


def test_m27_route_returns_a_search_tour(progress_client: TestClient) -> None:
    response = progress_client.get("/api/search?q=engines")
    assert response.status_code == 200
    payload = response.json()
    assert payload["engine"]["driver"] == "database"
    assert payload["engine"]["index"] == "posts"
    assert [hit["title"] for hit in payload["search"]["hits"]] == ["Notes on engines"]
    assert payload["collection_engine"] == ["Notes on engines"]
    assert payload["pagination"]["total"] >= 2
    assert payload["indexing"]["documents"]


def test_m27_board_marks_search_complete(progress_cwd: Path) -> None:
    del progress_cwd
    from app.http.controllers.progress_controller import _milestones

    m27 = next(m for m in _milestones() if m["id"] == "M27")
    assert m27["status"] == "complete"
    assert any("progress:search" in proof for proof in m27["proof"])
