"""M36 unit tests — kit overlays on the installer."""

from __future__ import annotations

from pathlib import Path

import pytest

from almasix.installer.kits import find_kit
from almasix.installer.options import Answers, resolve_plan
from almasix.installer.scaffold import ScaffoldError, scaffold_app


def test_find_kit_aliases() -> None:
    assert find_kit("livewire").name == "web"
    assert find_kit("signet").name == "api"
    assert find_kit("spa").frontend == "react"
    with pytest.raises(ScaffoldError):
        find_kit("angular")


def test_scaffold_web_kit_forces_auth_surface(tmp_path: Path) -> None:
    root = scaffold_app("webkit", destination=tmp_path / "webkit", kit="web", stack="tailwind")
    routes = (root / "routes" / "web.py").read_text(encoding="utf-8")
    assert "TwoFactorController" in routes
    assert "TeamController" in routes
    assert (root / "resources" / "views" / "settings" / "profile.prism.html").is_file()
    css = (root / "resources" / "css" / "app.css").read_text(encoding="utf-8")
    assert "0d9488" in css
    layout = (root / "resources" / "views" / "layouts" / "app.prism.html").read_text(
        encoding="utf-8"
    )
    assert "@conduit('theme_toggle')" in layout
    assert "theme_toggle" not in (
        root / "app" / "http" / "controllers" / "two_factor_controller.py"
    ).read_text(encoding="utf-8")
    assert (root / "app" / "conduit" / "theme_toggle.py").is_file()
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert "almasix[conduit]" in pyproject or "almasix-conduit" in pyproject
    routes = (root / "routes" / "web.py").read_text(encoding="utf-8")
    # Account delete confirms via form password — not password.confirm (no GET /user).
    destroy_idx = routes.index('Route.delete("/user"')
    confirm_block = routes.index('middleware=["password.confirm"]')
    assert destroy_idx < confirm_block
    profile_ctl = (root / "app" / "http" / "controllers" / "profile_controller.py").read_text(
        encoding="utf-8"
    )
    assert 'disk="public"' in profile_ctl
    assert "photo_action" in profile_ctl
    profile_view = (root / "resources" / "views" / "settings" / "profile.prism.html").read_text(
        encoding="utf-8"
    )
    assert "Save photo" in profile_view
    assert 'enctype="multipart/form-data"' in profile_view
    assert "photo_url_action" not in profile_view
    css = (root / "resources" / "css" / "app.css").read_text(encoding="utf-8")
    assert "Outfit" in css
    assert "JetBrains Mono" in css
    assert "Fraunces" not in css


def test_scaffold_api_kit_forces_none_stack(tmp_path: Path) -> None:
    root = scaffold_app("apikit", destination=tmp_path / "apikit", kit="api", stack="tailwind")
    # force_stack=none even if caller asked for tailwind
    assert not (root / "package.json").is_file()
    api = (root / "routes" / "api.py").read_text(encoding="utf-8")
    assert "auth:signet" in api


def test_scaffold_spa_react(tmp_path: Path) -> None:
    root = scaffold_app("spaapp", destination=tmp_path / "spaapp", kit="react")
    assert (root / "resources" / "js" / "Pages" / "Welcome.jsx").is_file()
    assert "InertiaServiceProvider" in (root / "config" / "app.py").read_text(encoding="utf-8")
    assert (root / "package.json").is_file()
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert "almasix[inertia]" in pyproject or "almasix-inertia" in pyproject


def test_resolve_plan_kit_flag(tmp_path: Path) -> None:
    plan = resolve_plan(
        "x",
        tmp_path / "x",
        Answers(kit="vue", database="sqlite"),
        interactive=False,
    )
    assert plan.kit == "vue"
    assert plan.stack == "tailwind"  # SPA force
