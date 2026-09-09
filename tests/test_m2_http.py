"""M2 HTTP + routing unit tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from almasix.framework import Application
from almasix.http import (
    BadRequestHttpException,
    HttpException,
    NotFoundHttpException,
    Request,
    html,
    json,
    make_response,
)
from almasix.http.exceptions import UnauthorizedHttpException
from almasix.routing import Route, Router, set_router
from tests.support import purge_generated_app_modules


def _make_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Application:
    purge_generated_app_modules()
    (tmp_path / ".env").write_text("APP_NAME=HttpApp\nAPP_DEBUG=true\n", encoding="utf-8")

    app_pkg = tmp_path / "app"
    (app_pkg / "http" / "controllers").mkdir(parents=True)
    (app_pkg / "http" / "middleware").mkdir(parents=True)
    for relative in (
        "__init__.py",
        "http/__init__.py",
        "http/controllers/__init__.py",
        "http/middleware/__init__.py",
    ):
        (app_pkg / relative).write_text("", encoding="utf-8")

    (app_pkg / "http" / "controllers" / "ping_controller.py").write_text(
        "from almasix.http import Controller, NotFoundHttpException, Request\n"
        "\n"
        "class PingController(Controller):\n"
        "    async def index(self):\n"
        "        return {'pong': 'ok'}\n"
        "\n"
        "    async def show(self, request: Request, id: str):\n"
        "        return {'id': id, 'path': request.path}\n"
        "\n"
        "    async def boom(self):\n"
        "        raise NotFoundHttpException('Missing resource')\n",
        encoding="utf-8",
    )
    (app_pkg / "http" / "middleware" / "tag_middleware.py").write_text(
        "from almasix.http import Middleware, Request\n"
        "\n"
        "class TagMiddleware(Middleware):\n"
        "    async def handle(self, request: Request, call_next):\n"
        "        response = await call_next(request)\n"
        "        response.headers['X-Tagged'] = '1'\n"
        "        return response\n",
        encoding="utf-8",
    )

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "app.py").write_text(
        'config = {"name": "HttpApp", "debug": True, "providers": []}\n',
        encoding="utf-8",
    )
    (config_dir / "http.py").write_text(
        "config = {\n"
        "    'middleware': [],\n"
        "    'middleware_aliases': {\n"
        "        'tag': 'app.http.middleware.tag_middleware.TagMiddleware',\n"
        "    },\n"
        "}\n",
        encoding="utf-8",
    )
    routes = tmp_path / "routes"
    routes.mkdir()
    (routes / "web.py").write_text(
        "from app.http.controllers.ping_controller import PingController\n"
        "from almasix.routing import Route\n"
        "\n"
        "Route.get('/', [PingController, 'index'])\n"
        "Route.get('/items/{id}', [PingController, 'show'])\n"
        "Route.get('/missing', [PingController, 'boom'])\n"
        "\n"
        "with Route.group(prefix='/api', middleware=['tag']):\n"
        "    Route.get('/ping', [PingController, 'index'])\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    sys.path.insert(0, str(tmp_path))
    monkeypatch.delenv("APP_NAME", raising=False)
    try:
        return Application(tmp_path).bootstrap()
    finally:
        pass


def test_route_dsl_groups_and_compile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        app = _make_app(tmp_path, monkeypatch)
        routes = {route.uri: route for route in app.router.routes}
        assert "/" in routes
        assert "/api/ping" in routes
        assert routes["/api/ping"].middleware_names == ["tag"]

        client = TestClient(app.asgi)
        assert client.get("/").json() == {"pong": "ok"}
        assert client.get("/items/42").json() == {"id": "42", "path": "/items/42"}

        tagged = client.get("/api/ping")
        assert tagged.json() == {"pong": "ok"}
        assert tagged.headers.get("x-tagged") == "1"
    finally:
        purge_generated_app_modules()
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))


def test_http_exception_json_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        app = _make_app(tmp_path, monkeypatch)
        client = TestClient(app.asgi)
        response = client.get("/missing")
        assert response.status_code == 404
        assert response.json() == {
            "message": "Missing resource",
            "status": 404,
            "errors": {},
        }
    finally:
        purge_generated_app_modules()
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))


def test_router_facade_requires_bootstrap() -> None:
    set_router(None)
    with pytest.raises(RuntimeError, match="Router is not set"):
        Route.get("/", lambda: {"ok": True})


def test_json_and_response_helpers() -> None:
    response = json({"ok": True}, status=201)
    assert response.status_code == 201
    assert make_response(None).status_code == 204
    assert make_response("hi").body == b"hi"
    assert make_response({"a": 1}).media_type == "application/json"
    assert make_response(b"xyz").body == b"xyz"

    page = html("<p>hi</p>", status=201, headers={"X-Page": "1"})
    assert page.status_code == 201
    assert page.media_type == "text/html"
    assert page.body == b"<p>hi</p>"
    assert page.headers["x-page"] == "1"
    # make_response passes an existing response through untouched.
    assert make_response(page) is page


def test_http_exception_payload() -> None:
    exc = BadRequestHttpException("Nope", errors={"field": ["required"]})
    assert exc.to_dict() == {
        "message": "Nope",
        "status": 400,
        "errors": {"field": ["required"]},
    }
    assert UnauthorizedHttpException().status_code == 401
    assert isinstance(NotFoundHttpException(), HttpException)


def test_router_methods_and_groups() -> None:
    router = Router()
    set_router(router)
    router.post("/a", lambda: None)
    router.put("/b", lambda: None)
    router.patch("/c", lambda: None)
    router.delete("/d", lambda: None)
    router.options("/e", lambda: None)
    router.match(["GET", "POST"], "/f", lambda: None)
    with router.group(prefix="v1", middleware=["auth"]):
        router.get("items", lambda: None)
    uris = {route.uri for route in router.routes}
    assert "/v1/items" in uris
    assert any(
        route.middleware_names == ["auth"] for route in router.routes if route.uri == "/v1/items"
    )
