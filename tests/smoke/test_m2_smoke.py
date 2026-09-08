"""M2 smoke — Almasix Route DSL without FastAPI imports in app code."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from almasix.installer.cli import app as almasix_app
from almasix.installer.scaffold import scaffold_app
from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke, pytest.mark.regression]

runner = CliRunner()


def test_m2_s1_scaffold_uses_route_dsl(tmp_path: Path) -> None:
    result = runner.invoke(almasix_app, ["new", "route_app", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.stdout
    root = tmp_path / "route_app"
    web = (root / "routes" / "web.py").read_text(encoding="utf-8")
    api = (root / "routes" / "api.py").read_text(encoding="utf-8")
    http_config = (root / "config" / "http.py").read_text(encoding="utf-8")
    bootstrap = (root / "bootstrap" / "app.py").read_text(encoding="utf-8")
    assert "Route.get" in web
    assert "from fastapi" not in bootstrap
    assert "application.asgi" in bootstrap
    assert "Application.configure" in bootstrap
    assert "with_middleware" in bootstrap
    # Route polarity: web groups render HTML, api groups return JSON.
    assert 'middleware=["web"]' in web
    assert 'prefix="/api", middleware=["api"]' in api
    # Locale resolution ships via bootstrap fluent middleware (M4).
    assert "SetLocaleMiddleware" in bootstrap
    assert 'append=["locale"]' in bootstrap
    assert '"web": []' in http_config
    assert '"api": []' in http_config
    assert (root / "lang" / "en" / "messages.py").is_file()
    assert "APP_LOCALE=" in (root / ".env").read_text(encoding="utf-8")


def test_m2_s2_progress_routes_via_kernel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Use the real progress example path relative to repo when available;
    # otherwise scaffold a fresh app with routes.
    root = scaffold_app("m2_smoke", destination=tmp_path / "m2_smoke")
    purge_generated_app_modules()
    monkeypatch.chdir(root)
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.delenv("APP_NAME", raising=False)
    try:
        module = importlib.import_module("bootstrap.app")
        assert module.application.is_bootstrapped
        client = TestClient(module.asgi)

        page = client.get("/")
        assert page.status_code == 200
        assert page.headers["content-type"].startswith("text/html")
        assert "Welcome to Almasix" in page.text

        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.headers["content-type"].startswith("application/json")
        assert health.json()["status"] == "ok"
        # Ensure no FastAPI in generated bootstrap
        assert "from fastapi" not in (root / "bootstrap" / "app.py").read_text(encoding="utf-8")
    finally:
        purge_generated_app_modules()


def test_m2_s3_progress_example_exhausts_http_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Living example: groups, middleware, verbs, Request, HttpException."""
    root = Path(__file__).resolve().parents[2] / "examples" / "progress"
    assert root.is_dir(), f"missing progress example at {root}"
    purge_generated_app_modules()
    monkeypatch.chdir(root)
    monkeypatch.syspath_prepend(str(root))
    # Process env wins over .env (override=False) — pin the living-example name.
    monkeypatch.setenv("APP_NAME", "Progress")
    without_base_path(monkeypatch)
    try:
        module = importlib.import_module("bootstrap.app")
        client = TestClient(module.asgi, raise_server_exceptions=False)

        # Web routes: HTML, no api middleware.
        home = client.get("/")
        assert home.status_code == 200
        assert home.headers["content-type"].startswith("text/html")
        assert "<h1>Progress tracker</h1>" in home.text
        assert "x-almasix-demo" not in home.headers

        board = client.get("/progress")
        assert board.status_code == 200
        assert board.headers["content-type"].startswith("text/html")
        assert "<h2>Milestones</h2>" in board.text
        assert "M2" in board.text

        # API routes: JSON, `api` middleware group expands to the demo.tag alias.
        # /api/health matches the scaffold HealthController; /api/ping keeps the M2 demo.
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.headers["content-type"].startswith("application/json")
        assert health.json()["status"] == "ok"
        assert health.json()["app"] == "Progress"
        assert health.headers.get("x-almasix-demo") == "m2"
        assert health.headers.get("x-almasix-path") == "/api/health"

        ping = client.get("/api/ping")
        assert ping.status_code == 200
        assert ping.json() == {"demo": "ping", "via": "controller"}
        assert ping.headers.get("x-almasix-demo") == "m2"

        data = client.get("/api/progress")
        assert data.headers["content-type"].startswith("application/json")
        assert data.json()["milestones"][2]["id"] == "M2"
        assert data.json()["milestones"][2]["status"] == "complete"

        show = client.get("/api/items/42?q=hello", headers={"Authorization": "Bearer secret"})
        assert show.status_code == 200
        assert show.json()["item"] == "42"
        assert show.json()["route"] == "42"
        assert show.json()["query"] == "hello"
        assert show.json()["bearer"] == "secret"
        assert show.json()["only_q"] == {"q": "hello"}

        created = client.post("/api/items", json={"name": "almasix", "flag": True, "count": 2})
        assert created.status_code == 200
        assert created.json()["created"] is True
        assert created.json()["name"] == "almasix"
        assert created.json()["boolean_flag"] is True
        assert created.json()["integer_count"] == 2

        bag = client.post("/api/bag?q=1", json={"name": "bag", "q": "body"})
        assert bag.status_code == 200
        assert bag.json()["all"]["q"] == "body"
        assert bag.json()["query"]["q"] == "1"
        assert bag.json()["post"]["name"] == "bag"
        assert bag.json()["has_name"] is True
        assert bag.json()["is_json"] is True

        di = client.get("/api/di")
        assert di.status_code == 200
        assert di.json()["injected"] == "ConfigRepository"
        assert di.json()["app_name"]

        assert client.put("/api/items/7").json() == {"updated": "7"}
        assert client.patch("/api/items/7").json() == {"patched": "7"}
        assert client.delete("/api/items/7").json() == {"deleted": "7"}
        assert client.options("/api/probe").json()["allow"].startswith("GET")
        assert client.get("/api/echo/9?q=api").json()["item"] == "9"

        invalid = client.post("/api/items", json={})
        assert invalid.status_code == 422
        assert invalid.json()["status"] == 422
        assert "name" in invalid.json()["errors"]

        # Error responses still pass back through the route middleware.
        boom = client.get("/api/boom")
        assert boom.status_code == 418
        assert boom.json() == {"message": "Intentional demo failure", "status": 418, "errors": {}}
        assert boom.headers.get("x-almasix-demo") == "m2"

        missing = client.get("/api/missing")
        assert missing.status_code == 404
        assert missing.json()["message"] == "Demo resource not found"

        assert "from fastapi" not in (root / "bootstrap" / "app.py").read_text(encoding="utf-8")
        assert "from fastapi" not in (root / "routes" / "web.py").read_text(encoding="utf-8")
        assert "from fastapi" not in (root / "routes" / "api.py").read_text(encoding="utf-8")
    finally:
        purge_generated_app_modules()
