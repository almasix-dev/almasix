"""Integration: view() through a booted Application."""

from __future__ import annotations

from pathlib import Path

from almasix.framework import Application
from almasix.prism import ViewFactory, render, view


def test_view_helper_with_application(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        'config = {"name": "CalDemo", "env": "testing", "debug": True}\n',
        encoding="utf-8",
    )
    (tmp_path / "config" / "http.py").write_text(
        'config = {"middleware": [], "middleware_groups": {"web": [], "api": []},'
        ' "route_middleware": {}}\n',
        encoding="utf-8",
    )
    (tmp_path / "config" / "database.py").write_text(
        'config = {"default": "sqlite", "connections": {"sqlite": {"driver": "sqlite",'
        ' "database": ":memory:"}}}\n',
        encoding="utf-8",
    )
    views = tmp_path / "resources" / "views"
    views.mkdir(parents=True)
    (views / "hello.prism.html").write_text("<p>{{ name }}</p>", encoding="utf-8")
    (tmp_path / "routes").mkdir()
    (tmp_path / "routes" / "web.py").write_text("", encoding="utf-8")
    (tmp_path / "routes" / "api.py").write_text("", encoding="utf-8")
    (tmp_path / "bootstrap").mkdir()
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "providers").mkdir()
    (tmp_path / "app" / "providers" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "providers" / "app_service_provider.py").write_text(
        "from almasix.providers import ServiceProvider\n"
        "class AppServiceProvider(ServiceProvider):\n"
        "    def register(self): pass\n"
        "    def boot(self): pass\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    app = Application.configure(tmp_path).create()
    assert app.make(ViewFactory) is not None
    assert render("hello", {"name": "World"}) == "<p>World</p>"
    response = view("hello", {"name": "World"})
    assert response.status_code == 200
    assert b"World" in response.body
