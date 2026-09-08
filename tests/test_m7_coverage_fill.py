"""Coverage fill for M7 session + auth surfaces."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response

from avalon.auth.guard import AuthManager, Guard, auth, get_auth, reset_auth, set_auth
from avalon.auth.middleware import Authenticate, RedirectIfAuthenticated, StartAuth
from avalon.auth.provider import AuthServiceProvider
from avalon.config import ConfigRepository, set_repository
from avalon.framework import Application
from avalon.http.request import Request
from avalon.session.signing import sign_payload, unsign_payload
from avalon.session.csrf import VerifyCsrfToken, csrf_token
from avalon.session.encrypt import decrypt_string, encrypt_string
from avalon.session.encrypt_middleware import EncryptCookies
from avalon.session.middleware import StartSession
from avalon.session.store import Session, get_session, reset_session, set_session


def _request(method: str = "GET", path: str = "/", *, cookies: dict | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers.append((b"cookie", cookie_header.encode("latin-1")))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(StarletteRequest(scope, receive))


@pytest.mark.asyncio
async def test_start_session_and_csrf_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    repo = ConfigRepository()
    repo.set("app.key", "test-key")
    repo.set("session.lifetime", 120)
    repo.set("session.cookie", "avalon_session")
    set_repository(repo)

    session_mw = StartSession()
    csrf_mw = VerifyCsrfToken()

    async def inner(request: Request) -> Response:
        assert request.session.get("_csrf_token")
        assert csrf_token()
        request.session.put("locale", "fr")
        request.session.flash("status", "hi")
        request.session.pull("missing", "x")
        request.session.forget("nope")
        request.session.flush()
        request.session.put("kept", 1)
        return Response("ok")

    async def after_csrf(request: Request) -> Response:
        return await csrf_mw.handle(request, inner)

    response = await session_mw.handle(_request(), after_csrf)
    assert response.status_code == 200
    assert "avalon_session" in (response.headers.get("set-cookie") or "")


@pytest.mark.asyncio
async def test_csrf_rejects_bad_token(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = ConfigRepository()
    repo.set("app.key", "test-key")
    set_repository(repo)
    session = Session({"_csrf_token": "expected"})
    request = _request("POST", "/")
    request._session = session  # noqa: SLF001
    token = set_session(session)
    try:
        with pytest.raises(Exception) as exc:
            await VerifyCsrfToken().handle(request, lambda r: Response("no"))
        assert getattr(exc.value, "status_code", None) == 419
    finally:
        reset_session(token)


@pytest.mark.asyncio
async def test_encrypt_cookies_middleware(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = ConfigRepository()
    repo.set("app.key", "enc-key")
    set_repository(repo)
    plain = "payload"
    encrypted = encrypt_string(plain, key="enc-key")
    assert decrypt_string("x.y", key="enc-key") is None

    mw = EncryptCookies()

    async def inner(request: Request) -> Response:
        assert request.cookie("demo") == plain
        response = Response("ok")
        response.set_cookie("demo", plain)
        response.set_cookie("skip", "raw")
        return response

    mw.except_cookies = frozenset({"skip"})  # type: ignore[misc]
    response = await mw.handle(_request(cookies={"demo": encrypted, "skip": "raw"}), inner)
    header = response.headers.get("set-cookie") or ""
    assert "demo=" in header


def test_cookie_unsign_edges() -> None:
    assert unsign_payload("a.b", key="k") is None
    import base64
    import hashlib
    import hmac
    import json
    import time

    from avalon.session import signing

    body = signing._b64encode(json.dumps({"a": 1}).encode())  # noqa: SLF001
    msg = f"{body}.notint"
    sig = signing._sign(msg, "k")  # noqa: SLF001
    assert unsign_payload(f"{body}.notint.{sig}", key="k") is None

    bad_body = signing._b64encode(b"\xff\xfe")  # noqa: SLF001
    ts = str(int(time.time()))
    msg2 = f"{bad_body}.{ts}"
    sig2 = signing._sign(msg2, "k")  # noqa: SLF001
    assert unsign_payload(f"{bad_body}.{ts}.{sig2}", key="k") is None

    # Non-dict JSON
    body3 = base64.urlsafe_b64encode(json.dumps([1]).encode()).decode().rstrip("=")
    ts3 = str(int(time.time()))
    msg3 = f"{body3}.{ts3}"
    sig3 = base64.urlsafe_b64encode(
        hmac.new(b"k", msg3.encode(), hashlib.sha256).digest()
    ).decode().rstrip("=")
    assert unsign_payload(f"{body3}.{ts3}.{sig3}", key="k") is None


def test_encrypt_invalid_utf8_payload() -> None:
    from avalon.session import encrypt as enc

    key = "k"
    raw_key = __import__("hashlib").sha256(key.encode()).digest()
    nonce = b"\x00" * 16
    cipher = bytes([0xFF, 0xFE])
    mac = __import__("hmac").new(raw_key, nonce + cipher, __import__("hashlib").sha256).digest()
    token = f"{enc._b64encode(nonce)}.{enc._b64encode(cipher)}.{enc._b64encode(mac)}"  # noqa: SLF001
    assert decrypt_string(token, key=key) is None


def test_user_to_dict_variants_and_guest() -> None:
    from avalon.auth import guest as guest_fn
    from avalon.auth.guard import _user_to_dict

    class WithDict:
        def to_dict(self):
            return {"id": 3}

    assert _user_to_dict(WithDict()) == {"id": 3}
    assert _user_to_dict(42) == {"user": "42"}
    assert guest_fn() is True

    manager = AuthManager()
    manager.guard("web").once({"id": 1})
    assert manager.id() == 1


def test_request_cookies_override() -> None:
    request = _request()
    request._cookies = {"a": "1"}  # noqa: SLF001
    assert request.cookies["a"] == "1"
    assert request.cookie("a") == "1"


def test_csrf_token_without_session(monkeypatch: pytest.MonkeyPatch) -> None:
    token = set_session(None)
    try:
        assert csrf_token() == ""
    finally:
        reset_session(token)

    session = Session()
    token = set_session(session)
    try:
        value = csrf_token()
        assert value
        assert session.get("_csrf_token") == value
    finally:
        reset_session(token)


def test_session_has_and_start_without_app_key(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Session({"x": 1})
    assert session.has("x")
    assert not session.has("y")

    repo = ConfigRepository()
    set_repository(repo)  # no app.key
    # covered via StartSession in async test below


@pytest.mark.asyncio
async def test_start_session_default_key(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = ConfigRepository()
    set_repository(repo)

    async def inner(request: Request) -> Response:
        request.session.put("n", 1)
        return Response("ok")

    response = await StartSession().handle(_request(), inner)
    assert "set-cookie" in {k.lower() for k in response.headers.keys()}


@pytest.mark.asyncio
async def test_encrypt_cookies_no_raw_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = ConfigRepository()
    repo.set("app.key", "k")
    set_repository(repo)
    mw = EncryptCookies()

    class Bare:
        raw_headers = None

        def __init__(self):
            self.status_code = 200

    async def inner(request: Request):
        return Bare()  # type: ignore[return-value]

    result = await mw.handle(_request(), inner)
    assert result.status_code == 200


@pytest.mark.asyncio
async def test_auth_middleware_redirects_and_json() -> None:
    request = _request("GET", "/dashboard")
    token = set_auth(AuthManager())
    try:
        response = await Authenticate().handle(request, _async_ok)
        assert response.status_code in {302, 303, 307}
    finally:
        reset_auth(token)

    api = _request("GET", "/api/secret")
    manager = AuthManager()
    token = set_auth(manager)
    try:
        with pytest.raises(Exception) as exc:
            await Authenticate().handle(api, _async_ok)
        assert getattr(exc.value, "status_code", None) == 401
    finally:
        reset_auth(token)

    manager = AuthManager()
    manager.guard("web").once({"id": 1})
    token = set_auth(manager)
    try:
        response = await RedirectIfAuthenticated().handle(_request("GET", "/login"), _async_ok)
        assert response.status_code in {302, 303, 307}
    finally:
        reset_auth(token)


async def _async_ok(request: Request) -> Response:
    return Response("ok")


@pytest.mark.asyncio
async def test_start_auth_from_session_and_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = ConfigRepository()
    repo.set("app.key", "k")
    set_repository(repo)
    session = Session({"login_web": {"id": "u1", "name": "U"}})
    request = _request()
    request._session = session  # noqa: SLF001

    async def inner(req: Request) -> Response:
        assert get_auth() is not None
        assert auth().check()
        return Response("ok")

    await StartAuth().handle(request, inner)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/me",
        "raw_path": b"/api/me",
        "query_string": b"",
        "headers": [(b"authorization", b"Bearer tok-1")],
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    bare = Request(StarletteRequest(scope, receive))
    bare._session = None  # noqa: SLF001

    async def bearer_inner(req: Request) -> Response:
        # Unknown bearer must not invent an opaque user (TokenGuard honesty).
        assert auth().guest()
        return Response("ok")

    await StartAuth().handle(bare, bearer_inner)


def test_auth_provider_boot_without_engine(tmp_path: Path) -> None:
    app = Application(tmp_path)
    AuthServiceProvider(app).register()
    AuthServiceProvider(app).boot()  # no engine — soft fail


def test_session_context_helpers() -> None:
    session = Session({"a": 1})
    token = set_session(session)
    assert get_session() is session
    assert bool(session)
    session.regenerate()
    assert session.dirty
    reset_session(token)
    assert get_session() is None


def test_request_session_requires_middleware() -> None:
    request = _request()
    with pytest.raises(RuntimeError, match="Session store not started"):
        _ = request.session
