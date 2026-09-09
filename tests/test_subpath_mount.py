"""APP_BASE_PATH ASGI mount."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from almasix.framework import Application
from almasix.http.controller import Controller
from almasix.http.subpath import mount_asgi, normalize_base_path
from almasix.routing import Route


def test_normalize_base_path() -> None:
    assert normalize_base_path("") == ""
    assert normalize_base_path("/") == ""
    assert normalize_base_path("almasix") == "/almasix"
    assert normalize_base_path("/almasix/") == "/almasix"


def test_mount_asgi_noop_without_prefix() -> None:
    sentinel = object()
    assert mount_asgi(sentinel, "") is sentinel
    assert mount_asgi(sentinel, "/") is sentinel


def test_kernel_mounts_app_at_base_path(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        'config = {"name": "MountApp", "debug": True, "base_path": "/almasix", "providers": []}\n',
        encoding="utf-8",
    )
    (tmp_path / "config" / "http.py").write_text(
        'config = {"middleware": [], "middleware_groups": {}, "middleware_aliases": {}}\n',
        encoding="utf-8",
    )
    (tmp_path / "routes").mkdir()

    class HomeController(Controller):
        async def index(self) -> dict[str, str]:
            return {"here": "home"}

    app = Application(tmp_path).bootstrap()
    app.router.routes.clear()
    Route.get("/", [HomeController, "index"])
    Route.get("/api/health", [HomeController, "index"])
    app.http_kernel._asgi = None

    client = TestClient(app.asgi)
    root = client.get("/", follow_redirects=False)
    assert root.status_code == 307
    assert root.headers["location"] == "/almasix/"

    assert client.get("/almasix/").json() == {"here": "home"}
    assert client.get("/almasix/api/health").json() == {"here": "home"}
    assert client.get("/api/health").status_code == 404
