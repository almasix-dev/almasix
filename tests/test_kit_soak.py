"""Unit coverage for ``almasix.installer.kit_soak`` (in-process, not subprocess)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from almasix.installer.kit_soak import (
    _follow,
    _login,
    _post,
    _purge_app_modules,
    _register,
    soak_auth,
)
from almasix.installer.scaffold import scaffold_app
from tests.support import purge_generated_app_modules


def _migrate(root: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "smith", "migrate", "--force"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "APP_BASE_PATH": ""},
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.fixture()
def web_kit(tmp_path: Path) -> Path:
    root = scaffold_app(
        "soakweb",
        destination=tmp_path / "soakweb",
        stack="tailwind",
        kit="web",
        tests=False,
    )
    _migrate(root)
    return root


@pytest.fixture()
def vue_kit(tmp_path: Path) -> Path:
    root = scaffold_app(
        "soakvue",
        destination=tmp_path / "soakvue",
        kit="vue",
        tests=False,
    )
    _migrate(root)
    return root


def test_soak_auth_web_kit(web_kit: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_BASE_PATH", "")
    purge_generated_app_modules()
    summary = soak_auth(web_kit, mode="web")
    assert "web auth soak ok" in summary
    purge_generated_app_modules()


def test_soak_auth_vue_kit(vue_kit: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_BASE_PATH", "")
    purge_generated_app_modules()
    summary = soak_auth(vue_kit, mode="spa")
    assert "spa auth soak ok" in summary
    purge_generated_app_modules()


def test_purge_app_modules_removes_bootstrap_and_app() -> None:
    sys.modules["bootstrap"] = object()  # type: ignore[assignment]
    sys.modules["bootstrap.app"] = object()  # type: ignore[assignment]
    sys.modules["app"] = object()  # type: ignore[assignment]
    sys.modules["app.models.user"] = object()  # type: ignore[assignment]
    _purge_app_modules()
    assert "bootstrap" not in sys.modules
    assert "bootstrap.app" not in sys.modules
    assert "app" not in sys.modules
    assert "app.models.user" not in sys.modules


def test_web_post_uses_form_token_and_xsrf_fallback(
    web_kit: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_BASE_PATH", "")
    purge_generated_app_modules()
    _purge_app_modules()
    if str(web_kit.resolve()) in sys.path:
        sys.path.remove(str(web_kit.resolve()))
    sys.path.insert(0, str(web_kit.resolve()))

    import importlib

    module = importlib.import_module("bootstrap.app")
    client = TestClient(module.asgi, raise_server_exceptions=False)

    # Form ``_token`` branch (register page).
    email = "token-branch@example.com"
    password = "secret-password-123"
    reg = _register(client, mode="web", email=email, password=password)
    assert reg.status_code in {200, 302, 303}

    # XSRF fallback: page with no ``_token`` (health) still carries XSRF-TOKEN.
    up = client.get("/up")
    assert up.status_code == 200
    assert "_token" not in up.text
    assert client.cookies.get("XSRF-TOKEN")
    logout = _post(client, mode="web", path="/logout", data={}, page="/up")
    assert logout.status_code in {200, 302, 303}

    # Login helper after logout.
    login = _login(client, mode="web", email=email, password=password)
    assert login.status_code in {200, 302, 303}
    purge_generated_app_modules()


def test_spa_post_sends_xsrf_header(vue_kit: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_BASE_PATH", "")
    purge_generated_app_modules()
    _purge_app_modules()
    if str(vue_kit.resolve()) in sys.path:
        sys.path.remove(str(vue_kit.resolve()))
    sys.path.insert(0, str(vue_kit.resolve()))

    import importlib

    module = importlib.import_module("bootstrap.app")
    client = TestClient(module.asgi, raise_server_exceptions=False)

    email = "spa-helper@example.com"
    password = "secret-password-123"
    reg = _register(client, mode="spa", email=email, password=password)
    assert reg.status_code in {200, 302, 303}
    logout = _post(client, mode="spa", path="/logout", data={}, page="/email/verify")
    assert logout.status_code in {200, 302, 303}
    login = _login(client, mode="spa", email=email, password=password)
    assert login.status_code in {200, 302, 303}
    purge_generated_app_modules()


def test_follow_redirect_chain_and_gate() -> None:
    calls: list[str] = []

    class _Client:
        def get(self, path: str, follow_redirects: bool = False):
            calls.append(path)
            if path == "/dashboard" and follow_redirects:
                return SimpleNamespace(
                    status_code=200,
                    text="Please verify email/verify",
                    url="http://test/email/verify",
                )
            if path == "/mid":
                return SimpleNamespace(
                    status_code=302,
                    headers={"location": "/dashboard"},
                    text="",
                    url="http://test/mid",
                )
            if path == "/dashboard":
                return SimpleNamespace(
                    status_code=200,
                    headers={},
                    text="ok",
                    url="http://test/dashboard",
                )
            return SimpleNamespace(status_code=200, text="ok", url=f"http://test{path}")

    first = SimpleNamespace(status_code=302, headers={"Location": "/mid"}, text="", url="")
    landed = _follow(_Client(), first, final_get="/dashboard")  # type: ignore[arg-type]
    assert calls == ["/mid", "/dashboard", "/dashboard"]
    assert "email/verify" in landed


def test_follow_stops_when_location_missing() -> None:
    class _Client:
        def get(self, path: str, follow_redirects: bool = False):
            return SimpleNamespace(
                status_code=200,
                text="verify notice",
                url="http://test/email/verify",
            )

    first = SimpleNamespace(status_code=302, headers={}, text="", url="")
    landed = _follow(_Client(), first, final_get="/dashboard")  # type: ignore[arg-type]
    assert "verify" in landed.lower()


def test_follow_breaks_on_non_redirect_status() -> None:
    class _Client:
        def get(self, path: str, follow_redirects: bool = False):
            return SimpleNamespace(
                status_code=200,
                text="email/verify",
                url="http://test/email/verify",
            )

    first = SimpleNamespace(status_code=200, headers={"location": "/x"}, text="ok", url="")
    landed = _follow(_Client(), first, final_get="/dashboard")  # type: ignore[arg-type]
    assert "email/verify" in landed


def test_follow_handles_307_and_empty_path() -> None:
    class _Client:
        def get(self, path: str, follow_redirects: bool = False):
            if path == "/":
                return SimpleNamespace(
                    status_code=200, headers={}, text="landed", url="http://test/"
                )
            return SimpleNamespace(
                status_code=200,
                text="email/verify",
                url="http://test/email/verify",
            )

    first = SimpleNamespace(
        status_code=307, headers={"location": "https://example.com"}, text="", url=""
    )
    landed = _follow(_Client(), first, final_get="/dashboard")  # type: ignore[arg-type]
    assert "email/verify" in landed or "verify" in landed.lower()


def test_follow_exhausts_redirect_budget() -> None:
    """Eight hops without a non-redirect response still proceeds to the gate GET."""

    class _Client:
        def get(self, path: str, follow_redirects: bool = False):
            if follow_redirects:
                return SimpleNamespace(
                    status_code=200,
                    text="email/verify",
                    url="http://test/email/verify",
                )
            return SimpleNamespace(
                status_code=308,
                headers={"location": path},
                text="",
                url=f"http://test{path}",
            )

    first = SimpleNamespace(status_code=308, headers={"location": "/loop"}, text="", url="")
    landed = _follow(_Client(), first, final_get="/dashboard")  # type: ignore[arg-type]
    assert "email/verify" in landed


def test_soak_auth_clears_blank_and_duplicate_sys_path(
    web_kit: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_BASE_PATH", "")
    purge_generated_app_modules()
    root = str(web_kit.resolve())
    sys.path.insert(0, "")
    sys.path.insert(0, root)
    sys.path.insert(0, root)
    summary = soak_auth(web_kit, mode="web")
    assert "web auth soak ok" in summary
    purge_generated_app_modules()


def test_soak_auth_rejects_missing_csrf(web_kit: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bare POST without CSRF is asserted inside soak_auth (419)."""
    monkeypatch.setenv("APP_BASE_PATH", "")
    purge_generated_app_modules()
    # Full soak includes the 419 assertion at the start.
    assert "ok" in soak_auth(web_kit, mode="web")
    purge_generated_app_modules()
