"""M7 exhaust — remember-me cookies, events, argon2, request.user, intended URL."""

from __future__ import annotations

import pytest
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response

from almasix.auth import (
    Attempting,
    Failed,
    Login,
    Logout,
    auth,
    forget,
    listen,
    pull_intended_url,
    store_intended_url,
)
from almasix.auth.cookies import apply_queued_cookies, begin_cookie_queue, reset_cookie_queue
from almasix.auth.guard import AuthManager, SessionGuard, TokenGuard, reset_auth, set_auth
from almasix.auth.middleware import Authenticate, StartAuth
from almasix.auth.providers import MemoryUserProvider
from almasix.hashing import Hash, HashManager, set_hash_manager
from almasix.http.request import Request
from almasix.session.store import Session, reset_session, set_session


@pytest.fixture(autouse=True)
def _fast_hash() -> None:
    manager = HashManager()
    manager.configure(rounds=4)
    set_hash_manager(manager)
    forget()
    yield
    set_hash_manager(None)
    forget()


def _req(path="/", *, headers=None, method="GET") -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": list(headers or []),
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(StarletteRequest(scope, receive))


@pytest.mark.asyncio
async def test_remember_me_queues_set_cookie() -> None:
    provider = MemoryUserProvider(
        [{"id": 1, "email": "a@b.c", "password": Hash.make("secret")}]
    )
    guard = SessionGuard("web", provider)
    session = Session()
    tok = set_session(session)
    cookie_tok = begin_cookie_queue()
    try:
        assert await guard.attempt({"email": "a@b.c", "password": "secret"}, remember=True)
        response = Response("ok")
        apply_queued_cookies(response)
        header = response.headers.get("set-cookie", "")
        assert "remember_web=" in header
        assert "|" in header
        user = provider.users[0]
        assert user.get("remember_token")
    finally:
        reset_session(tok)
        reset_cookie_queue(cookie_tok)


@pytest.mark.asyncio
async def test_remember_cookie_hydrates_across_requests() -> None:
    provider = MemoryUserProvider(
        [
            {
                "id": 1,
                "email": "a@b.c",
                "password": Hash.make("secret"),
                "remember_token": "tok-abc",
            }
        ]
    )
    request = _req(headers=[(b"cookie", b"remember_web=1|tok-abc")])
    request._session = Session()  # noqa: SLF001
    request._cookies = {"remember_web": "1|tok-abc"}  # noqa: SLF001

    async def inner(req: Request) -> Response:
        # StartAuth builds its own manager; inject provider via via_request fallback
        # by patching after — instead resolve through Memory provider on manager.
        manager = auth()
        manager._providers["users"] = provider  # noqa: SLF001
        web = SessionGuard("web", provider)
        manager._guards["web"] = web  # noqa: SLF001
        remembered = await provider.retrieve_by_token("1", "tok-abc")
        assert remembered is not None
        web.once(remembered)
        web._via_remember = True  # noqa: SLF001
        assert auth().via_remember() or web.via_remember()
        return Response("ok")

    # Direct hydrate path
    from almasix.auth.middleware import _from_remember_cookie

    web = SessionGuard("web", provider)
    user = await _from_remember_cookie(request, web)
    assert user is not None
    assert user["id"] == 1


@pytest.mark.asyncio
async def test_token_guard_rejects_unknown_bearer() -> None:
    provider = MemoryUserProvider(
        [{"id": 1, "email": "a@b.c", "api_token": "secret-token", "password": Hash.make("x")}]
    )
    guard = TokenGuard("api", provider)
    assert await guard.set_user_from_request_token("nope") is None
    assert guard.guest()
    assert await guard.set_user_from_request_token("secret-token") is not None
    assert guard.check()


@pytest.mark.asyncio
async def test_auth_events_fire_on_attempt_login_logout() -> None:
    seen: list[str] = []

    def on_attempting(event: Attempting) -> None:
        seen.append("attempting")

    def on_failed(event: Failed) -> None:
        seen.append("failed")

    def on_login(event: Login) -> None:
        seen.append("login")

    def on_logout(event: Logout) -> None:
        seen.append("logout")

    listen(Attempting, on_attempting)
    listen(Failed, on_failed)
    listen(Login, on_login)
    listen(Logout, on_logout)

    provider = MemoryUserProvider(
        [{"id": 1, "email": "a@b.c", "password": Hash.make("secret")}]
    )
    guard = SessionGuard("web", provider)
    session = Session()
    tok = set_session(session)
    try:
        assert not await guard.attempt({"email": "a@b.c", "password": "wrong"})
        assert await guard.attempt({"email": "a@b.c", "password": "secret"})
        await guard.logout()
    finally:
        reset_session(tok)

    assert "attempting" in seen
    assert "failed" in seen
    assert "login" in seen
    assert "logout" in seen


@pytest.mark.asyncio
async def test_request_user_and_intended_url() -> None:
    provider = MemoryUserProvider(
        [{"id": 1, "email": "a@b.c", "password": Hash.make("secret")}]
    )
    manager = AuthManager()
    web = SessionGuard("web", provider)
    manager._guards["web"] = web  # noqa: SLF001
    web.once({"id": 1, "email": "a@b.c"})
    request = _req("/settings")
    request._auth = manager  # noqa: SLF001
    assert request.user()["id"] == 1
    assert request.user("web")["id"] == 1

    session = Session()
    tok = set_session(session)
    auth_tok = set_auth(manager)
    try:
        store_intended_url("/settings?tab=security")
        assert pull_intended_url() == "/settings?tab=security"
        assert pull_intended_url("/fallback") == "/fallback"
    finally:
        reset_session(tok)
        reset_auth(auth_tok)


@pytest.mark.asyncio
async def test_authenticate_stores_intended_url() -> None:
    from almasix.config import ConfigRepository, set_repository

    repo = ConfigRepository()
    repo.set("app.url", "http://localhost")
    set_repository(repo)
    session = Session()
    tok = set_session(session)
    request = _req("/dashboard")
    request._session = session  # noqa: SLF001
    try:

        async def ok(req):
            return Response("ok")

        response = await Authenticate().handle(request, ok)
        assert response.status_code in {302, 303, 307}
        assert session.get("url.intended") == "/dashboard"
    finally:
        reset_session(tok)
        set_repository(None)


def test_argon2_hasher_roundtrip() -> None:
    pytest.importorskip("argon2")
    manager = HashManager()
    manager.configure(driver="argon2id", argon_memory=8192, argon_threads=1, argon_time=1)
    set_hash_manager(manager)
    hashed = Hash.make("secret")
    assert hashed.startswith("$argon2")
    assert Hash.check("secret", hashed)
    assert not Hash.check("nope", hashed)
    assert Hash.is_hashed(hashed)
    assert Hash.driver("argon2").is_hashed(hashed)


@pytest.mark.asyncio
async def test_via_request_custom_guard() -> None:
    manager = AuthManager()

    async def resolve(request):
        return {"id": "via", "name": "Custom"}

    manager.via_request("custom", resolve)
    request = _req()
    request._session = Session()  # noqa: SLF001

    # Wire StartAuth path manually
    guard = manager.guard("custom")
    assert guard._via_request is resolve  # noqa: SLF001
    resolved = await resolve(request)
    guard.once(resolved)
    assert manager.guard("custom").user()["id"] == "via"


@pytest.mark.asyncio
async def test_start_auth_applies_remember_cookie_from_login() -> None:
    provider = MemoryUserProvider(
        [{"id": 7, "email": "ada@almasix.dev", "password": Hash.make("password")}]
    )
    session = Session()
    request = _req()
    request._session = session  # noqa: SLF001

    async def login_then(req: Request) -> Response:
        manager = auth()
        manager._providers["users"] = provider  # noqa: SLF001
        web = SessionGuard("web", provider)
        manager._guards["web"] = web  # noqa: SLF001
        assert await web.attempt(
            {"email": "ada@almasix.dev", "password": "password"},
            remember=True,
        )
        return Response("logged-in")

    response = await StartAuth().handle(request, login_then)
    set_cookie = response.headers.get("set-cookie", "")
    assert "remember_web=" in set_cookie
