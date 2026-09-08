"""M2 route polarity — web returns HTML, api returns JSON; middleware groups."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from almasix.framework import Application
from almasix.http import Controller, Middleware, NotFoundHttpException, Request, Response, html
from almasix.http.kernel import HttpKernel
from almasix.routing import Route, Router, set_router
from tests.support import purge_generated_app_modules


class PageController(Controller):
    async def show(self) -> Response:
        return html("<h1>Almasix</h1>")


class DataController(Controller):
    async def show(self) -> dict[str, str]:
        return {"status": "ok"}

    async def missing(self) -> dict[str, str]:
        raise NotFoundHttpException("Nope")


class StampMiddleware(Middleware):
    async def handle(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Stamp"] = "api"
        return response


def _boot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Application:
    purge_generated_app_modules()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        'config = {"name": "Polarity", "debug": False, "providers": []}\n',
        encoding="utf-8",
    )
    (tmp_path / "config" / "http.py").write_text(
        "from tests.test_m2_polarity import StampMiddleware\n"
        "config = {\n"
        "    'middleware': [],\n"
        "    'middleware_groups': {'web': [], 'api': ['stamp']},\n"
        "    'middleware_aliases': {'stamp': StampMiddleware},\n"
        "}\n",
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
    return app


def test_web_serves_html_and_api_serves_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _boot(tmp_path, monkeypatch)
    with Route.group(middleware=["web"]):
        Route.get("/", [PageController, "show"])
    with Route.group(prefix="/api", middleware=["api"]):
        Route.get("/health", [DataController, "show"])
        Route.get("/missing", [DataController, "missing"])
    app._routes_loaded = True

    client = TestClient(app.asgi, raise_server_exceptions=False)

    page = client.get("/")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert page.text == "<h1>Almasix</h1>"
    # The `web` group is empty until sessions land, so no api stamp leaks in.
    assert "x-stamp" not in page.headers

    data = client.get("/api/health")
    assert data.status_code == 200
    assert data.headers["content-type"].startswith("application/json")
    assert data.json() == {"status": "ok"}
    # Proves the `api` group expanded to its alias member.
    assert data.headers["x-stamp"] == "api"

    # HttpException converts inside the pipeline, so middleware still sees it.
    missing = client.get("/api/missing")
    assert missing.status_code == 404
    assert missing.json() == {"message": "Nope", "status": 404, "errors": {}}
    assert missing.headers["x-stamp"] == "api"


def test_middleware_groups_expand_recursively_and_reject_cycles() -> None:
    kernel = HttpKernel(Application(), Router())
    groups = {"web": ["session", "csrf"], "admin": ["web", "can:admin"]}

    assert kernel._expand_groups(["admin", "throttle"], groups) == [
        "session",
        "csrf",
        "can:admin",
        "throttle",
    ]
    # Non-group entries (including classes) pass through untouched.
    assert kernel._expand_groups([StampMiddleware], groups) == [StampMiddleware]

    with pytest.raises(RuntimeError, match="Circular middleware group"):
        kernel._expand_groups(["a"], {"a": ["b"], "b": ["a"]})
