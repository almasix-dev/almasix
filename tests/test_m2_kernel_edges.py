"""Additional kernel edge-case coverage for M2."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from almasix.framework import Application
from almasix.http import Controller, Middleware, Request
from almasix.routing import Route, set_router
from tests.support import purge_generated_app_modules


class EchoController(Controller):
    async def index(self) -> dict[str, str]:
        return {"echo": "1"}


class TypeAliasMiddleware(Middleware):
    async def handle(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Type-Mw"] = "yes"
        return response


async def bare_handler() -> dict[str, str]:
    return {"bare": "ok"}


def test_callable_and_string_actions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    purge_generated_app_modules()
    (tmp_path / ".env").write_text("APP_NAME=Edges\nAPP_DEBUG=false\n", encoding="utf-8")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        'config = {"name": "Edges", "debug": False, "providers": []}\n',
        encoding="utf-8",
    )
    (tmp_path / "config" / "http.py").write_text(
        "from tests.test_m2_kernel_edges import TypeAliasMiddleware\n"
        "config = {'middleware': [], 'middleware_aliases': {'typed': TypeAliasMiddleware}}\n",
        encoding="utf-8",
    )
    (tmp_path / "routes").mkdir()
    # Load routes after bootstrap via manual registration to avoid import path pain
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("APP_NAME", raising=False)
    app = Application(tmp_path)
    app.load_environment()
    app.load_configuration()
    app.register_configured_providers()
    app.boot()
    set_router(app.router)

    Route.get("/bare", bare_handler)
    Route.get("/ctrl", "tests.test_m2_kernel_edges.EchoController@index")
    with Route.group(middleware=["typed"]):
        Route.get("/typed", [EchoController, "index"])

    # Force exception path in debug mode
    async def explode() -> dict[str, str]:
        raise RuntimeError("boom-debug")

    Route.get("/explode", explode)

    app._routes_loaded = True  # noqa: SLF001
    client = TestClient(app.asgi, raise_server_exceptions=False)
    assert client.get("/bare").json() == {"bare": "ok"}
    assert client.get("/ctrl").json() == {"echo": "1"}
    typed = client.get("/typed")
    assert typed.json() == {"echo": "1"}
    assert typed.headers.get("x-type-mw") == "yes"
    exploded = client.get("/explode")
    assert exploded.status_code == 500
    assert exploded.json()["message"] == "Server Error"
    assert exploded.json()["status"] == 500


def test_http_exception_status_override() -> None:
    from almasix.http import HttpException

    exc = HttpException("x", status_code=418)
    assert exc.status_code == 418


def test_kernel_invalid_action_and_middleware() -> None:
    from almasix.http.kernel import HttpKernel
    from almasix.routing import Router

    app = Application()
    kernel = HttpKernel(app, Router())
    with pytest.raises(TypeError, match="Unsupported route action"):
        kernel._resolve_action(123)  # noqa: SLF001
    with pytest.raises(ImportError, match="Invalid import path"):
        kernel._resolve_middleware("missing", {})  # noqa: SLF001
    with pytest.raises(RuntimeError, match="Unknown middleware"):
        kernel._resolve_middleware("weird", {"weird": 42})  # noqa: SLF001
    with pytest.raises(TypeError, match="Middleware subclass"):
        kernel._resolve_middleware("bad", {"bad": dict})  # noqa: SLF001


def test_kernel_asgi_cached_and_sync_handlers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    purge_generated_app_modules()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        'config = {"name": "Sync", "debug": False, "providers": []}\n',
        encoding="utf-8",
    )
    (tmp_path / "config" / "http.py").write_text(
        "config = {'middleware': [], 'middleware_aliases': {}}\n",
        encoding="utf-8",
    )
    (tmp_path / "routes").mkdir()
    monkeypatch.chdir(tmp_path)
    app = Application(tmp_path)
    app.load_environment()
    app.load_configuration()
    app.register_configured_providers()
    app.boot()
    set_router(app.router)

    def sync_ok() -> dict[str, str]:
        return {"sync": "ok"}

    Route.get("/sync", sync_ok)
    Route.get("/ctrl-list", [EchoController, "index"])
    Route.get("/ctrl-str", ["tests.test_m2_kernel_edges.EchoController", "index"])

    app._routes_loaded = True  # noqa: SLF001
    first = app.asgi
    second = app.asgi
    assert first is second
    client = TestClient(first)
    assert client.get("/sync").json() == {"sync": "ok"}
    assert client.get("/ctrl-list").json() == {"echo": "1"}
    assert client.get("/ctrl-str").json() == {"echo": "1"}


def test_request_json_and_form(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    purge_generated_app_modules()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        'config = {"name": "Body", "debug": False, "providers": []}\n',
        encoding="utf-8",
    )
    (tmp_path / "config" / "http.py").write_text(
        "config = {'middleware': [], 'middleware_aliases': {}}\n",
        encoding="utf-8",
    )
    (tmp_path / "routes").mkdir()
    monkeypatch.chdir(tmp_path)
    app = Application(tmp_path)
    app.load_environment()
    app.load_configuration()
    app.register_configured_providers()
    app.boot()
    set_router(app.router)

    async def echo_json(request: Request) -> dict[str, object]:
        return {"json": request.json()}

    async def echo_form(request: Request) -> dict[str, object]:
        return {"name": request.post("name")}

    Route.post("/json", echo_json)
    Route.post("/form", echo_form)
    app._routes_loaded = True  # noqa: SLF001
    client = TestClient(app.asgi)
    assert client.post("/json", json={"a": 1}).json() == {"json": {"a": 1}}
    assert client.post("/json", content=b"not-json", headers={"content-type": "application/json"}).json() == {
        "json": None
    }
    assert client.post("/form", data={"name": "almasix"}).json() == {"name": "almasix"}
