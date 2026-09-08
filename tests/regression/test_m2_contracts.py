"""Locked M2 public contracts — HTTP + routing."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from almasix.http import Controller, HttpKernel, Middleware, Request, UploadedFile, html, json
from almasix.installer.scaffold import scaffold_app
from almasix.routing import Route, Router

pytestmark = [pytest.mark.regression]


def test_m2_public_exports() -> None:
    assert Controller is not None
    assert Middleware is not None
    assert Request is not None
    assert UploadedFile is not None
    assert HttpKernel is not None
    assert Route is not None
    assert Router is not None
    assert hasattr(Request, "all")
    assert hasattr(Request, "only")
    assert hasattr(Request, "except_")
    assert hasattr(Request, "create")
    # Route polarity helpers: web renders HTML, api returns JSON.
    assert html("<b>x</b>").media_type == "text/html"
    assert json({"a": 1}).media_type == "application/json"


def test_nested_groups_compose_prefix_and_middleware() -> None:
    router = Router()
    with router.group(prefix="/api", middleware=["throttle"]):
        with router.group(prefix="/v1", middleware=["auth"]):
            router.get("/users", lambda: None, name="users.index")
        router.get("health", lambda: None, middleware=["cache"])
    router.get("/", lambda: None)

    users, health, home = router.routes

    assert users.uri == "/api/v1/users"
    assert users.middleware == ["throttle", "auth"]
    assert users.name == "users.index"

    # Sibling route sees only the outer group; the inner stack frame is popped.
    assert health.uri == "/api/health"
    assert health.middleware == ["throttle", "cache"]

    # Group stack fully unwound outside the `with` blocks.
    assert home.uri == "/"
    assert home.middleware == []


def test_scaffold_m2_bootstrap_has_no_fastapi(tmp_path: Path) -> None:
    root = scaffold_app("m2_contract", destination=tmp_path / "m2_contract")
    bootstrap = (root / "bootstrap" / "app.py").read_text(encoding="utf-8")
    web = (root / "routes" / "web.py").read_text(encoding="utf-8")
    api = (root / "routes" / "api.py").read_text(encoding="utf-8")
    assert "from fastapi" not in bootstrap
    assert "asgi = application.asgi" in bootstrap
    assert "Route.get" in web
    assert "html(" in (root / "app" / "http" / "controllers" / "welcome_controller.py").read_text(
        encoding="utf-8"
    )
    assert "Route.get" in api
    assert (root / "app" / "http" / "controllers" / "health_controller.py").is_file()
    assert (root / "config" / "http.py").exists()


def test_scaffolded_app_serves_via_route_dsl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.support import purge_generated_app_modules
    import importlib

    root = scaffold_app("m2_serve", destination=tmp_path / "m2_serve")
    purge_generated_app_modules()
    monkeypatch.chdir(root)
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.delenv("APP_NAME", raising=False)
    try:
        module = importlib.import_module("bootstrap.app")
        client = TestClient(module.asgi)

        page = client.get("/")
        assert page.headers["content-type"].startswith("text/html")
        assert "Welcome to Almasix" in page.text
        assert "M2Serve" in page.text

        health = client.get("/api/health")
        assert health.headers["content-type"].startswith("application/json")
        assert health.json() == {"status": "ok", "app": "M2Serve", "env": "local"}
    finally:
        purge_generated_app_modules()
