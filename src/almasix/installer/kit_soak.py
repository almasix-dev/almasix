"""HTTP auth soak for a freshly scaffolded starter kit.

Used by ``smith progress:kits`` (and callable from a clean subprocess) so
register → logout → login is proven for Web (Prism) and SPA (Inertia) kits —
not only that the files exist.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi.testclient import TestClient

Mode = Literal["web", "spa"]


def soak_auth(root: Path | str, *, mode: Mode) -> str:
    """Boot ``root`` and exercise CSRF + register + logout + login.

    Returns a one-line summary. Raises ``AssertionError`` on failure.
    """
    app_root = Path(root).resolve()
    _purge_app_modules()
    # Ensure the scaffold wins over any previously imported app package.
    while "" in sys.path:
        sys.path.remove("")
    if str(app_root) in sys.path:
        sys.path.remove(str(app_root))
    sys.path.insert(0, str(app_root))

    import importlib

    module = importlib.import_module("bootstrap.app")
    client = TestClient(module.asgi, raise_server_exceptions=False)

    email = f"soak-{mode}@example.com"
    password = "secret-password-123"

    # Missing CSRF must 419.
    bare = client.post(
        "/register",
        data={
            "name": "Soak",
            "email": email,
            "password": password,
            "password_confirmation": password,
        },
    )
    assert bare.status_code == 419, f"expected 419 without CSRF, got {bare.status_code}"

    register = _register(client, mode=mode, email=email, password=password)
    assert register.status_code in {200, 302, 303}, (
        f"register failed: {register.status_code} {register.text[:200]}"
    )
    # MustVerifyEmail → dashboard is gated; follow to the verify notice.
    landed = _follow(client, register, final_get="/dashboard")
    assert "email/verify" in landed or "Verify" in landed or "verify" in landed.lower(), (
        f"expected email verification after register, got: {landed[:240]}"
    )

    # Logout (CSRF-protected POST — mint token from a GET-able page).
    logout = _post(client, mode=mode, path="/logout", data={}, page="/email/verify")
    assert logout.status_code in {200, 302, 303}, f"logout failed: {logout.status_code}"

    # Login again with the same credentials.
    login = _login(client, mode=mode, email=email, password=password)
    assert login.status_code in {200, 302, 303}, (
        f"login failed: {login.status_code} {login.text[:200]}"
    )
    landed = _follow(client, login, final_get="/dashboard")
    assert "email/verify" in landed or "Verify" in landed or "verify" in landed.lower(), (
        f"expected email verification after login, got: {landed[:240]}"
    )

    return f"{mode} auth soak ok (register→verify, logout, login→verify)"


def _register(client: TestClient, *, mode: Mode, email: str, password: str):
    data = {
        "name": "Soak User",
        "email": email,
        "password": password,
        "password_confirmation": password,
    }
    return _post(client, mode=mode, path="/register", data=data, page="/register")


def _login(client: TestClient, *, mode: Mode, email: str, password: str):
    data = {"email": email, "password": password}
    return _post(client, mode=mode, path="/login", data=data, page="/login")


def _post(
    client: TestClient,
    *,
    mode: Mode,
    path: str,
    data: dict[str, str],
    page: str | None = None,
):
    """POST with the CSRF mechanism that kit uses in the browser."""
    page = page or path
    warm = client.get(page)
    assert warm.status_code == 200, f"GET {page} -> {warm.status_code}"

    if mode == "web":
        match = re.search(r'name=["\']_token["\']\s+value=["\']([^"\']+)["\']', warm.text)
        if match is None:
            match = re.search(r'value=["\']([^"\']+)["\']\s+name=["\']_token["\']', warm.text)
        if match:
            return client.post(
                path, data={**data, "_token": match.group(1)}, follow_redirects=False
            )
        # Logout (and other POSTs without a form) still have XSRF-TOKEN.
        xsrf = client.cookies.get("XSRF-TOKEN")
        assert xsrf, f"no _token on {page} and no XSRF-TOKEN cookie"
        return client.post(
            path,
            data=data,
            headers={"X-XSRF-TOKEN": xsrf},
            follow_redirects=False,
        )

    # SPA / Inertia: axios sends X-XSRF-TOKEN from the XSRF-TOKEN cookie.
    xsrf = client.cookies.get("XSRF-TOKEN")
    assert xsrf, "XSRF-TOKEN cookie missing after GET (VerifyCsrfToken must mint it)"
    headers = {
        "X-XSRF-TOKEN": xsrf,
        "X-Inertia": "true",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "text/html, application/xhtml+xml",
    }
    return client.post(path, json=data, headers=headers, follow_redirects=False)


def _follow(client: TestClient, response, *, final_get: str) -> str:
    """Follow Location redirects, then GET ``final_get`` for the gated landing page."""
    current = response
    for _ in range(8):
        if current.status_code not in {301, 302, 303, 307, 308}:
            break
        location = current.headers.get("location") or current.headers.get("Location")
        if not location:
            break
        path = urlparse(location).path or "/"
        current = client.get(path, follow_redirects=False)
    # Authenticated but unverified users hitting dashboard land on /email/verify.
    gate = client.get(final_get, follow_redirects=True)
    return f"{gate.url} {gate.status_code} {gate.text}"


def _purge_app_modules() -> None:
    for key in list(sys.modules):
        if (
            key == "bootstrap"
            or key.startswith("bootstrap.")
            or key == "app"
            or key.startswith("app.")
        ):
            del sys.modules[key]
