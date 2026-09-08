"""M7 smoke — session login with attempt(), CSRF, bearer/token auth."""

from __future__ import annotations

import asyncio
import importlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke, pytest.mark.regression]

PROGRESS = Path(__file__).resolve().parents[2] / "examples" / "progress"


@pytest.fixture()
def progress_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    monkeypatch.setenv("DB_CONNECTION", "sqlite")
    monkeypatch.setenv("DB_DATABASE", str(tmp_path / "m7_smoke.sqlite"))
    monkeypatch.setenv("APP_KEY", "base64:progress-m7-smoke-key")
    module = importlib.import_module("bootstrap.app")
    from app.support.demo_db import ensure_demo_database

    asyncio.run(ensure_demo_database())
    return TestClient(module.asgi)


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="_token"\s+value="([^"]+)"', html)
    assert match, "expected @csrf hidden field"
    return match.group(1)


def test_m7_login_logout_session_flow(progress_client: TestClient) -> None:
    home = progress_client.get("/")
    assert home.status_code == 200
    assert "Browsing as guest" in home.text

    login_page = progress_client.get("/login")
    assert login_page.status_code == 200
    token = _csrf_from_html(login_page.text)

    rejected = progress_client.post(
        "/login",
        data={"email": "ada@almasix.dev", "password": "password"},
    )
    assert rejected.status_code == 419

    signed_in = progress_client.post(
        "/login",
        data={
            "_token": token,
            "email": "ada@almasix.dev",
            "password": "password",
        },
        follow_redirects=True,
    )
    assert signed_in.status_code == 200
    assert "Signed in as Ada" in signed_in.text or "Ada" in signed_in.text

    guest_blocked = progress_client.get("/login", follow_redirects=False)
    assert guest_blocked.status_code in {302, 303, 307}

    out = progress_client.get("/logout", follow_redirects=True)
    assert out.status_code == 200
    assert "Browsing as guest" in out.text


def test_m7_api_bearer_auth(progress_client: TestClient) -> None:
    denied = progress_client.get("/api/me")
    assert denied.status_code == 401

    ok = progress_client.get("/api/me", headers={"Authorization": "Bearer secret-token"})
    assert ok.status_code == 200
    body = ok.json()["user"]
    assert body.get("api_token") == "secret-token" or body.get("token") == "secret-token" or body.get(
        "email"
    ) == "ada@almasix.dev"


def test_m7_session_cookie_is_set(progress_client: TestClient) -> None:
    response = progress_client.get("/")
    assert response.status_code == 200
    assert "almasix_session" in response.cookies or any(
        "almasix_session" in (m or "") for m in response.headers.get_list("set-cookie")
    )
