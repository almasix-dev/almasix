"""M6 smoke — Prism view() on the progress example web routes."""

from __future__ import annotations

import importlib
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


def test_m6_welcome_renders_prism(progress_client: TestClient) -> None:
    response = progress_client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Progress tracker" in response.text
    assert "almasix-banner.svg" in response.text
    assert "theme-toggle" in response.text
    assert "Milestone board" in response.text
    assert "css/app.css" in response.text
    assert "<!doctype html>" in response.text.lower()
    assert "@extends" not in response.text
    assert "@yield" not in response.text


def test_m6_progress_board_renders_prism(progress_client: TestClient) -> None:
    response = progress_client.get("/progress")
    assert response.status_code == 200
    assert "Milestones" in response.text
    assert "Prism" in response.text
    assert "@section" not in response.text


def test_m6_showcase_and_public_assets(progress_client: TestClient) -> None:
    page = progress_client.get("/showcase")
    assert page.status_code == 200
    assert "Prism showcase" in page.text
    assert "smith make:component" in page.text
    assert 'name="description"' in page.text
    assert "Prism showcase loaded" in page.text
    assert "Named slots" in page.text
    assert "data-method" in page.text
    assert "badge" in page.text.lower()

    css = progress_client.get("/css/app.css")
    assert css.status_code == 200
    assert "data-theme" in css.text

    logo = progress_client.get("/images/almasix-banner.svg")
    assert logo.status_code == 200
    assert "Almasix" in logo.text

    js = progress_client.get("/js/app.js")
    assert js.status_code == 200
    assert "almasix-theme" in js.text


def test_m6_prism_assets_honor_base_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Subpath smoke: asset() URLs and static mounts under APP_BASE_PATH."""
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    monkeypatch.setenv("APP_BASE_PATH", "/apps/progress")
    monkeypatch.setenv("APP_URL", "http://testserver")
    # Force re-import with new env.
    for mod in list(importlib.sys.modules):
        if mod == "bootstrap" or mod.startswith("bootstrap.") or mod == "config" or mod.startswith("config."):
            importlib.sys.modules.pop(mod, None)
    import sys

    for mod in list(sys.modules):
        if mod in {"bootstrap", "bootstrap.app", "config", "config.app"} or mod.startswith(
            ("bootstrap.", "config.", "app.")
        ):
            sys.modules.pop(mod, None)

    module = importlib.import_module("bootstrap.app")
    client = TestClient(module.asgi)

    home = client.get("/apps/progress/", follow_redirects=True)
    assert home.status_code == 200
    assert 'href="/apps/progress/css/app.css"' in home.text or "/apps/progress/css/app.css" in home.text
    assert "/apps/progress/images/almasix-banner.svg" in home.text

    css = client.get("/apps/progress/css/app.css")
    assert css.status_code == 200
    assert "--accent" in css.text or "data-theme" in css.text

    logo = client.get("/apps/progress/images/almasix-banner.svg")
    assert logo.status_code == 200
