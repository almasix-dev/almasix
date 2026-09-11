"""Broad M7 auth/hashing/password coverage for the parity ladder."""

from __future__ import annotations

import base64

import pytest
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response

from almasix.auth.authenticatable import AuthenticatableMixin
from almasix.auth.guard import Guard, SessionGuard, TokenGuard, auth_failed_message
from almasix.auth.middleware import (
    Authenticate,
    AuthenticateWithBasicAuth,
    RedirectIfAuthenticated,
    RequirePassword,
    mark_password_confirmed,
)
from almasix.auth.passwords import (
    DatabaseTokenRepository,
    Password,
    PasswordBroker,
)
from almasix.auth.providers import ArticulateUserProvider, MemoryUserProvider
from almasix.config import ConfigRepository, set_repository
from almasix.hashing import Hash, HashManager, set_hash_manager
from almasix.http.request import Request
from almasix.session.store import Session, reset_session, set_session


@pytest.fixture(autouse=True)
def _fast_hash() -> None:
    manager = HashManager()
    manager.configure(rounds=4)
    set_hash_manager(manager)
    yield
    set_hash_manager(None)


def _req(method="GET", path="/", *, headers=None, session=None) -> Request:
    hdrs = list(headers or [])
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": hdrs,
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request(StarletteRequest(scope, receive))
    if session is not None:
        request._session = session
    return request


class DummyUser(AuthenticatableMixin):
    def __init__(self, **attrs):
        self._attrs = dict(attrs)

    def get_attribute(self, key, default=None):
        return self._attrs.get(key, default)

    def set_attribute(self, key, value):
        self._attrs[key] = value

    async def save(self):
        return self

    @property
    def id(self):
        return self._attrs.get("id")

    def to_dict(self):
        return dict(self._attrs)


class DummyQuery:
    def __init__(self, users):
        self.users = users
        self._filters = {}

    def where(self, key, value):
        self._filters[key] = value
        return self

    async def find(self, identifier):
        for user in self.users:
            if user.get_auth_identifier() == identifier:
                return user
        return None

    async def first(self):
        for user in self.users:
            ok = all(user.get_attribute(k) == v for k, v in self._filters.items())
            if ok:
                return user
        return None


class DummyModel:
    users: list = []

    @classmethod
    def query(cls):
        return DummyQuery(cls.users)


@pytest.mark.asyncio
async def test_articulate_provider_and_session_guard_paths() -> None:
    user = DummyUser(
        id=1,
        email="a@b.c",
        name="A",
        password=Hash.make("pw"),
        remember_token=None,
    )
    DummyModel.users = [user]
    provider = ArticulateUserProvider(DummyModel)
    assert await provider.retrieve_by_id(1) is user
    assert await provider.retrieve_by_credentials({"email": "a@b.c"}) is user
    assert await provider.validate_credentials(user, {"password": "pw"})
    assert not await provider.validate_credentials(user, {"password": "no"})
    await provider.rehash_password_if_required(user, {"password": "pw"}, force=True)
    await provider.update_remember_token(user, "tok")
    assert user.get_remember_token() == "tok"
    assert await provider.retrieve_by_token(1, "tok") is user

    session = Session()
    token = set_session(session)
    try:
        guard = SessionGuard("web", provider)
        assert await guard.login_using_id(1, remember=True)
        assert guard.check()
        assert await guard.validate({"email": "a@b.c", "password": "pw"})
        assert await guard.logout_other_devices("pw")
        assert not await guard.logout_other_devices("bad")
        await guard.once_using_id(1)
        await guard.logout()
        assert guard.guest()
    finally:
        reset_session(token)


@pytest.mark.asyncio
async def test_token_guard_and_basic_auth_middleware() -> None:
    provider = MemoryUserProvider(
        [{"id": 1, "email": "a@b.c", "password": Hash.make("pw"), "api_token": "t1"}]
    )
    guard = TokenGuard("api", provider)
    assert await guard.attempt({"api_token": "t1"})
    assert guard.check()
    assert await guard.validate({"token": "t1"})

    set_repository(ConfigRepository())
    request = _req(
        headers=[
            (
                b"authorization",
                b"Basic " + base64.b64encode(b"a@b.c:pw"),
            )
        ]
    )
    from almasix.auth.guard import AuthManager, reset_auth, set_auth

    manager = AuthManager()
    manager._providers["users"] = provider
    manager._guards["web"] = SessionGuard("web", provider)
    tok = set_auth(manager)
    try:

        async def ok(req):
            return Response("ok")

        response = await AuthenticateWithBasicAuth().handle(request, ok)
        assert response.status_code == 200
        denied = await AuthenticateWithBasicAuth().handle(_req(), ok)
        assert denied.status_code == 401
    finally:
        reset_auth(tok)


@pytest.mark.asyncio
async def test_password_confirm_redirects_to_named_route() -> None:
    """Kit routes may live at /user/confirm-password; middleware must follow the name."""
    from almasix.routing import Route
    from almasix.routing.router import Router, get_router, set_router

    previous = None
    try:
        previous = get_router()
    except RuntimeError:
        pass
    router = Router()
    set_router(router)
    Route.get("/user/confirm-password", lambda: "ok", name="password.confirm")

    session = Session()
    request = _req(path="/user/two-factor-authentication", session=session)
    token = set_session(session)
    try:

        async def ok(req):
            return Response("ok")

        redirected = await RequirePassword(timeout=10).handle(request, ok)
        assert redirected.status_code in {302, 303, 307}
        assert redirected.headers.get("location", "").endswith("/user/confirm-password")
    finally:
        reset_session(token)
        if previous is not None:
            set_router(previous)
        else:
            set_router(Router())


@pytest.mark.asyncio
async def test_password_confirm_mutating_uses_referer_as_intended() -> None:
    """DELETE/POST cannot be replayed after confirm — store Referer, not the mutate path."""
    from almasix.auth.guard import pull_intended_url

    session = Session()
    request = _req(
        method="DELETE",
        path="/user",
        session=session,
        headers=[(b"referer", b"http://localhost/user/profile")],
    )
    token = set_session(session)
    try:

        async def ok(req):
            return Response("ok")

        redirected = await RequirePassword(timeout=10).handle(request, ok)
        assert redirected.status_code in {302, 303, 307}
        assert pull_intended_url("/dashboard") == "/user/profile"
    finally:
        reset_session(token)


@pytest.mark.asyncio
async def test_password_confirm_and_guest_named_guard() -> None:
    session = Session()
    request = _req(session=session)
    token = set_session(session)
    try:

        async def ok(req):
            return Response("ok")

        redirected = await RequirePassword(timeout=10).handle(request, ok)
        assert redirected.status_code in {302, 303, 307}
        assert redirected.headers.get("location", "").endswith("/confirm-password")
        mark_password_confirmed(request)
        allowed = await RequirePassword(timeout=10).handle(request, ok)
        assert allowed.status_code == 200
    finally:
        reset_session(token)

    from almasix.auth.guard import AuthManager, reset_auth, set_auth

    manager = AuthManager()
    manager.guard("web").once({"id": 1})
    tok = set_auth(manager)
    try:

        async def ok(req):
            return Response("ok")

        response = await RedirectIfAuthenticated("web").handle(_req(), ok)
        assert response.status_code in {302, 303, 307}
        allowed = await RedirectIfAuthenticated("api").handle(_req(), ok)
        assert allowed.status_code == 200
        authed = await Authenticate("web").handle(_req(), ok)
        assert authed.status_code == 200
    finally:
        reset_auth(tok)


@pytest.mark.asyncio
async def test_password_broker_edges() -> None:
    provider = MemoryUserProvider([{"id": 1, "email": "a@b.c", "password": Hash.make("old")}])
    tokens = DatabaseTokenRepository(expire=60, throttle=60)
    assert await tokens.delete_expired() == 0
    broker = PasswordBroker(provider, tokens)

    async def deliver(user, token):
        deliver.token = token

    broker.send_callback = deliver
    assert await broker.send_reset_link({"email": "nope"}) == Password.INVALID_USER
    assert await broker.send_reset_link({"email": "a@b.c"}) == Password.RESET_LINK_SENT
    assert await broker.send_reset_link({"email": "a@b.c"}) == Password.RESET_THROTTLED
    assert Password.status_message(Password.RESET_LINK_SENT)

    async def apply(user, password):
        user["password"] = Hash.make(password)

    assert (
        await broker.reset(
            {"email": "a@b.c", "token": "bad", "password": "x"},
            apply,
        )
        == Password.INVALID_TOKEN
    )
    assert (
        await broker.reset(
            {"email": "a@b.c", "token": deliver.token, "password": "new"},
            apply,
        )
        == Password.PASSWORD_RESET
    )
    await tokens.create("z@z.z")
    tokens._tokens["z@z.z"]["created_at"] = 0
    assert await tokens.delete_expired() >= 1


def test_hash_errors_and_auth_message() -> None:
    with pytest.raises(RuntimeError):
        Hash.check("x", "not-a-hash")
    assert Hash.needs_rehash("not-a-hash")
    assert auth_failed_message()
    manager = HashManager()
    with pytest.raises(RuntimeError):
        manager.driver("scrypt-not-a-driver")


def test_authenticatable_mixin_fallback() -> None:
    class Plain(AuthenticatableMixin):
        id = 9
        password = "x"
        remember_token = "r"

    plain = Plain()
    assert plain.get_auth_identifier() == 9
    assert plain.get_auth_password() == "x"
    plain.set_remember_token("n")
    assert plain.get_remember_token() == "n"

    from almasix.auth.contracts import Authenticatable

    assert isinstance(DummyUser(id=1, password="p"), Authenticatable)


@pytest.mark.asyncio
async def test_remember_cookie_hydrate_and_manager_helpers() -> None:
    from almasix.auth.guard import AuthManager
    from almasix.auth.middleware import StartAuth

    provider = MemoryUserProvider(
        [
            {
                "id": "1",
                "email": "a@b.c",
                "password": Hash.make("pw"),
                "remember_token": "rem",
            }
        ]
    )
    manager = AuthManager()
    manager._providers["users"] = provider
    web = SessionGuard("web", provider)
    manager._guards["web"] = web
    api = TokenGuard("api", provider)
    manager._guards["api"] = api
    await api.set_user_from_request_token("missing")
    assert not api.check()
    api.once({"id": "1", "token": "x"})
    assert manager.check()
    assert manager.user() is not None
    assert manager.id() is not None

    request = _req(headers=[(b"cookie", b"remember_web=1|rem")])
    request._session = Session()

    # Force StartAuth to use our provider via config-less resolve by patching guard
    async def ok(req):
        # StartAuth builds its own manager — just ensure it doesn't crash
        return Response("ok")

    await StartAuth().handle(request, ok)

    # Base Guard NotImplemented
    bare = Guard("x")
    with pytest.raises(NotImplementedError):
        await bare.attempt({})
    with pytest.raises(NotImplementedError):
        await bare.validate({})


@pytest.mark.asyncio
async def test_auth_manager_attempt_validate_via_auth_helper() -> None:
    from almasix.auth.guard import AuthManager, auth, reset_auth, set_auth

    provider = MemoryUserProvider([{"id": 1, "email": "a@b.c", "password": Hash.make("pw")}])
    manager = AuthManager()
    manager._default = "web"
    manager._guards["web"] = SessionGuard("web", provider)
    session = Session()
    token = set_session(session)
    tok = set_auth(manager)
    try:
        assert await auth().validate({"email": "a@b.c", "password": "pw"})
        assert await auth().attempt({"email": "a@b.c", "password": "pw"})
        await auth().logout()
    finally:
        reset_auth(tok)
        reset_session(token)
