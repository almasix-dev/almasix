"""Fluent Application.configure().with_middleware() bootstrap."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from almasix.framework import Application, Middleware
from almasix.http import (
    HEADER_X_FORWARDED_FOR,
    HEADER_X_FORWARDED_PROTO,
    Middleware as HttpMiddleware,
    Request,
)
from almasix.http.controller import Controller
from almasix.installer.scaffold import scaffold_app
from almasix.routing import Route
from tests.support import purge_generated_app_modules, without_base_path


class _TagMiddleware(HttpMiddleware):
    async def handle(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Fluent"] = "1"
        return response


def test_with_middleware_merges_into_http_config(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        'config = {"name": "Fluent", "debug": True, "providers": []}\n',
        encoding="utf-8",
    )
    (tmp_path / "config" / "http.py").write_text(
        'config = {"middleware": [], "middleware_groups": {"web": [], "api": []}, '
        '"middleware_aliases": {}}\n',
        encoding="utf-8",
    )
    (tmp_path / "routes").mkdir()
    # No route files required — this test only asserts config merge.

    def configure(middleware: Middleware) -> None:
        middleware.alias({"tag": _TagMiddleware})
        middleware.web(append=["tag"])
        middleware.api(prepend=["tag"])
        middleware.append("tag")

    app = Application.configure(tmp_path).with_middleware(configure).create()
    assert app.config.get("http.middleware_aliases")["tag"] is _TagMiddleware
    assert app.config.get("http.middleware_groups")["web"] == ["tag"]
    assert app.config.get("http.middleware_groups")["api"] == ["tag"]
    assert app.config.get("http.middleware") == ["tag"]


def test_scaffold_bootstrap_registers_locale_via_fluent_api(tmp_path: Path) -> None:
    root = scaffold_app("fluent_app", destination=tmp_path / "fluent_app")
    bootstrap = (root / "bootstrap" / "app.py").read_text(encoding="utf-8")
    assert "Application.configure" in bootstrap
    assert "with_middleware" in bootstrap
    assert "SetLocaleMiddleware" in bootstrap
    assert "trust_proxies" in bootstrap
    assert "trust_hosts" in bootstrap
    http = (root / "config" / "http.py").read_text(encoding="utf-8")
    assert "middleware_aliases" in http
    assert "SetLocaleMiddleware" not in http


def test_trust_proxies_rewrites_client_and_scheme(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        'config = {"name": "ProxyApp", "debug": True, "providers": []}\n',
        encoding="utf-8",
    )
    (tmp_path / "config" / "http.py").write_text(
        'config = {"middleware": [], "middleware_groups": {"web": [], "api": []}, '
        '"middleware_aliases": {}}\n',
        encoding="utf-8",
    )
    (tmp_path / "routes").mkdir()

    class ProbeController(Controller):
        async def index(self, request: Request) -> dict[str, object]:
            return {
                "ip": request.ip(),
                "scheme": request.raw.url.scheme,
            }

    def configure(middleware: Middleware) -> None:
        middleware.trust_proxies(
            at="*",
            headers=HEADER_X_FORWARDED_FOR | HEADER_X_FORWARDED_PROTO,
        )

    app = Application.configure(tmp_path).with_middleware(configure).create()
    assert app.config.get("http.trusted_proxies") == "*"
    assert app.config.get("http.trusted_headers") == (
        HEADER_X_FORWARDED_FOR | HEADER_X_FORWARDED_PROTO
    )

    app.router.routes.clear()
    Route.get("/probe", [ProbeController, "index"])
    app.http_kernel._asgi = None  # noqa: SLF001
    client = TestClient(app.asgi)
    response = client.get(
        "/probe",
        headers={
            "X-Forwarded-For": "203.0.113.9",
            "X-Forwarded-Proto": "https",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"ip": "203.0.113.9", "scheme": "https"}


def test_trust_hosts_rejects_unknown_host(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        'config = {"name": "HostApp", "debug": True, "providers": []}\n',
        encoding="utf-8",
    )
    (tmp_path / "config" / "http.py").write_text(
        'config = {"middleware": [], "middleware_groups": {"web": [], "api": []}, '
        '"middleware_aliases": {}}\n',
        encoding="utf-8",
    )
    (tmp_path / "routes").mkdir()

    class OkController(Controller):
        async def index(self) -> dict[str, str]:
            return {"ok": "1"}

    def configure(middleware: Middleware) -> None:
        middleware.trust_hosts(at=["app.test", "*.almasix.dev"])

    app = Application.configure(tmp_path).with_middleware(configure).create()
    assert app.config.get("http.trusted_hosts") == ["app.test", "*.almasix.dev"]
    assert "trust.hosts" in app.config.get("http.middleware")

    app.router.routes.clear()
    Route.get("/", [OkController, "index"])
    app.http_kernel._asgi = None  # noqa: SLF001
    client = TestClient(app.asgi, raise_server_exceptions=False)

    allowed = client.get("/", headers={"Host": "app.test"})
    assert allowed.status_code == 200
    assert allowed.json() == {"ok": "1"}

    wildcard = client.get("/", headers={"Host": "demo.almasix.dev"})
    assert wildcard.status_code == 200

    denied = client.get("/", headers={"Host": "evil.example"})
    assert denied.status_code == 400
    assert denied.json()["status"] == 400


def test_progress_fluent_middleware_still_tags_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib

    root = Path(__file__).resolve().parents[1] / "examples" / "progress"
    purge_generated_app_modules()
    monkeypatch.chdir(root)
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.delenv("APP_NAME", raising=False)
    without_base_path(monkeypatch)
    monkeypatch.setenv("DB_DATABASE", str(tmp_path / "fluent.sqlite"))
    try:
        module = importlib.import_module("bootstrap.app")
        client = TestClient(module.asgi)
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.headers.get("x-almasix-demo") == "m2"
        home = client.get("/")
        assert home.status_code == 200
        assert "x-almasix-demo" not in {k.lower(): v for k, v in home.headers.items()}
    finally:
        purge_generated_app_modules()
