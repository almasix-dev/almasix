"""M3 — `python smith make:*` generators."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from almasix.smith.cli import app as smith_app
from almasix.smith.make import MakeError, make
from tests.support import purge_generated_app_modules

runner = CliRunner()


def test_generators_write_importable_classes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purge_generated_app_modules()
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))

    for command, name, relative in (
        ("make:controller", "PostController", "app/http/controllers/post_controller.py"),
        ("make:middleware", "EnsureToken", "app/http/middleware/ensure_token.py"),
        ("make:provider", "RouteServiceProvider", "app/providers/route_service_provider.py"),
        ("make:request", "StorePostRequest", "app/http/requests/store_post_request.py"),
    ):
        result = runner.invoke(smith_app, [command, name])
        assert result.exit_code == 0, result.stdout
        assert relative in result.stdout
        assert (tmp_path / relative).is_file()

    # Generated directories are importable packages.
    assert (tmp_path / "app" / "http" / "requests" / "__init__.py").is_file()

    try:
        from app.http.controllers.post_controller import PostController
        from app.http.middleware.ensure_token import EnsureToken
        from app.http.requests.store_post_request import StorePostRequest
        from app.providers.route_service_provider import RouteServiceProvider

        from almasix.http import Controller, Middleware
        from almasix.providers import ServiceProvider
        from almasix.validation import FormRequest

        assert issubclass(PostController, Controller)
        assert issubclass(EnsureToken, Middleware)
        assert issubclass(RouteServiceProvider, ServiceProvider)
        assert issubclass(StorePostRequest, FormRequest)
        assert PostController.__doc__ == "PostController."
        assert "name" in StorePostRequest.__schema__.model_fields
    finally:
        purge_generated_app_modules()
        sys.modules.pop("app", None)


def test_nested_namespace_and_force(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(smith_app, ["make:controller", "Admin/UserController"]).exit_code == 0
    target = tmp_path / "app" / "http" / "controllers" / "admin" / "user_controller.py"
    assert target.is_file()
    assert (tmp_path / "app" / "http" / "controllers" / "admin" / "__init__.py").is_file()

    duplicate = runner.invoke(smith_app, ["make:controller", "Admin/UserController"])
    assert duplicate.exit_code == 1
    assert "already exists" in duplicate.stderr

    target.write_text("# edited\n", encoding="utf-8")
    forced = runner.invoke(smith_app, ["make:controller", "Admin/UserController", "--force"])
    assert forced.exit_code == 0
    assert "# edited" not in target.read_text(encoding="utf-8")


def test_invalid_names_are_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    bad = runner.invoke(smith_app, ["make:request", "9Bad"])
    assert bad.exit_code == 1
    assert "Invalid name segment" in bad.stderr

    with pytest.raises(MakeError, match="class name is required"):
        make("controller", "/", base_path=tmp_path)
    with pytest.raises(MakeError, match="Unknown generator"):
        make("widget", "Post", base_path=tmp_path)


def test_make_component_writes_anonymous_view(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(smith_app, ["make:component", "forms/Input"])
    assert result.exit_code == 0, result.stdout
    target = tmp_path / "resources" / "views" / "components" / "forms" / "input.prism.html"
    assert target.is_file()
    body = target.read_text(encoding="utf-8")
    assert "@props" in body
    assert "{{ slot }}" in body

    duplicate = runner.invoke(smith_app, ["make:component", "forms/Input"])
    assert duplicate.exit_code == 1
    assert "already exists" in duplicate.stderr

    forced = runner.invoke(smith_app, ["make:component", "forms/Input", "--force"])
    assert forced.exit_code == 0


def test_make_component_class_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(smith_app, ["make:component", "Alert", "--class"])
    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "resources" / "views" / "components" / "alert.prism.html").is_file()
    class_path = tmp_path / "app" / "view" / "components" / "alert.py"
    assert class_path.is_file()
    assert "class Alert(Component)" in class_path.read_text(encoding="utf-8")
