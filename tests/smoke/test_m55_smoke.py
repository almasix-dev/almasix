"""M55 smoke — almasix-inertia demo, X-Inertia JSON, board, docs."""

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
INERTIA = ROOT / "packages" / "inertia"
runner = CliRunner()


def _prepend_packages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(PROGRESS))
    for pkg in ("courier", "inertia"):
        monkeypatch.syspath_prepend(str(ROOT / "packages" / pkg / "src"))


@pytest.fixture()
def progress_cwd(monkeypatch: pytest.MonkeyPatch) -> Path:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    _prepend_packages(monkeypatch)
    from almasix.console.kernel import ConsoleKernel

    ConsoleKernel.from_cwd(PROGRESS).register_on_typer(smith_app)
    return PROGRESS


@pytest.fixture()
def progress_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    _prepend_packages(monkeypatch)
    module = importlib.import_module("bootstrap.app")
    app = module.application
    app._asgi = None
    module.asgi = app.asgi
    return TestClient(module.asgi, raise_server_exceptions=False)


def test_m55_progress_inertia_command(progress_cwd: Path) -> None:
    result = runner.invoke(smith_app, ["progress:inertia"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "inertia ok" in result.stdout


def test_m55_inertia_html_shell(progress_client: TestClient) -> None:
    response = progress_client.get("/inertia")
    assert response.status_code == 200
    assert b'data-page="' in response.content or b'id="app"' in response.content
    assert b"Welcome" in response.content


def test_m55_inertia_json_visit(progress_client: TestClient) -> None:
    response = progress_client.get("/inertia", headers={"X-Inertia": "true"})
    assert response.status_code == 200
    data = response.json()
    assert data["component"] == "Welcome"
    assert data["props"]["framework"] == "almasix"
    assert "stats" not in data["props"]  # lazy omitted on full visit
    assert "feed" in data.get("deferredProps", {}).get("default", [])
    assert response.headers.get("x-inertia") == "true"


def test_m55_inertia_partial_lazy(progress_client: TestClient) -> None:
    response = progress_client.get(
        "/inertia",
        headers={
            "X-Inertia": "true",
            "X-Inertia-Partial-Component": "Welcome",
            "X-Inertia-Partial-Data": "stats,feed",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["props"]["stats"] == {"visits": 42}
    assert data["props"]["feed"] == [{"id": 1}]
    assert "framework" not in data["props"]


def test_m55_inertia_version_mismatch_409(progress_client: TestClient) -> None:
    response = progress_client.get(
        "/inertia",
        headers={"X-Inertia": "true", "X-Inertia-Version": "stale-asset-version"},
    )
    assert response.status_code == 409
    assert "X-Inertia-Location" in response.headers or "x-inertia-location" in {
        k.lower() for k in response.headers
    }


def test_m55_board_marks_inertia_complete(progress_client: TestClient) -> None:
    data = progress_client.get("/api/progress").json()
    by_id = {m["id"]: m for m in data["milestones"]}
    assert by_id["M55"]["status"] == "complete"
    assert any("progress:inertia" in p for p in by_id["M55"]["proof"])


def test_m55_docs_and_package_exist() -> None:
    assert (DOCS / "inertia.md").is_file()
    assert (INERTIA / "src" / "inertia" / "provider.py").is_file()
    assert (INERTIA / "src" / "inertia" / "ssr" / "server.js").is_file()
    assert (INERTIA / "EXTRACT.md").is_file()
    sidebar = (ROOT / "website" / "astro.config.mjs").read_text(encoding="utf-8")
    assert "inertia" in sidebar
    docs = (DOCS / "inertia.md").read_text(encoding="utf-8")
    assert "lazy" in docs.lower() and "defer" in docs.lower()
    assert "APP_BASE_PATH" in docs or "subpath" in docs.lower()
