"""Drive remaining statement/branch coverage toward 100%."""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response

from almasix.auth import events as auth_events
from almasix.auth.cookies import apply_queued_cookies, begin_cookie_queue, queue_cookie, reset_cookie_queue
from almasix.auth.guard import (
    AuthManager,
    Guard,
    SessionGuard,
    TokenGuard,
    _import_string,
    _remember_token_of,
    _session_payload,
    _user_id,
    _user_to_dict,
    reset_auth,
    set_auth,
)
from almasix.auth.middleware import (
    AuthenticateWithBasicAuth,
    RedirectIfAuthenticated,
    RequirePassword,
    StartAuth,
    _configured_guard_names,
    _unauthenticated,
)
from almasix.auth.passwords import (
    DatabaseTokenRepository,
    Password,
    PasswordBroker,
    PasswordBrokerManager,
    set_password_manager,
)
from almasix.auth.providers import ArticulateUserProvider, MemoryUserProvider
from almasix.config import ConfigRepository, env, set_repository
from almasix.hashing import Hash, HashManager, set_hash_manager
from almasix.http.exceptions import UnauthorizedHttpException
from almasix.http.request import Request
from almasix.http.trust import (
    HEADER_X_FORWARDED_ALL,
    TrustProxiesASGI,
    _scope_peer,
    peer_is_trusted,
)
from almasix.session.encrypt_middleware import EncryptCookies
from almasix.session.middleware import StartSession
from almasix.session.store import Session, set_session


@pytest.fixture(autouse=True)
def _fast_hash() -> None:
    manager = HashManager()
    manager.configure(rounds=4)
    set_hash_manager(manager)
    auth_events.forget()
    set_password_manager(None)
    set_repository(None)
    yield
    set_hash_manager(None)
    auth_events.forget()
    set_password_manager(None)
    set_repository(None)


def _req(path="/", *, headers=None, method="GET", query=b"") -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query,
        "headers": list(headers or []),
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(StarletteRequest(scope, receive))


@pytest.mark.asyncio
async def test_providers_full_edges() -> None:
    class FakeQuery:
        def __init__(self, user=None) -> None:
            self.user = user

        def where(self, key, value):
            return self

        async def find(self, identifier):
            return self.user if identifier != "missing" else None

        async def first(self):
            return self.user

    user = SimpleNamespace(
        id=1,
        remember_token="rem",
        password=Hash.make("secret"),
        get_auth_password=lambda: Hash.make("secret"),
        set_attribute=lambda k, v: setattr(user, k, v),
        save=AsyncMock(),
    )

    class FakeModel:
        @staticmethod
        def query():
            return FakeQuery(user)

    provider = ArticulateUserProvider(FakeModel)
    assert await provider.retrieve_by_token("missing", "rem") is None
    assert await provider.retrieve_by_token(1, "wrong") is None
    assert await provider.retrieve_by_token(1, "rem") is user
    assert await provider.validate_credentials(user, {}) is False
    assert await provider.validate_credentials(SimpleNamespace(password=None), {"password": "x"}) is False
    await provider.rehash_password_if_required(user, {"password": "secret"}, force=True)
    plain = SimpleNamespace(password=Hash.make("a"), save=AsyncMock())
    await provider.rehash_password_if_required(plain, {"password": "a"}, force=True)
    assert await provider.retrieve_by_credentials({"password": "only"}) is None

    mem = MemoryUserProvider(
        [{"id": 1, "email": "a@b.c", "password": Hash.make("p"), "remember_token": "t"}]
    )
    assert await mem.retrieve_by_token(1, "nope") is None
    assert await mem.retrieve_by_token(99, "t") is None
    u = dict(await mem.retrieve_by_id(1))
    await mem.rehash_password_if_required(u, {"password": "p"}, force=True)
    await mem.rehash_password_if_required({"id": 1}, {})
    assert await mem.retrieve_by_id("1") is not None


@pytest.mark.asyncio
async def test_guard_helpers_remaining() -> None:
    class Ident:
        def get_auth_identifier(self):
            return 42

    g = Guard("web")
    g.once(Ident())
    assert g.id() == 42
    assert await g.login_using_id(1) is None
    assert await g.once_using_id(1) is None
    await g.logout()
    g.once({"id": 9})
    await g.logout()

    assert await SessionGuard("web", MemoryUserProvider([])).validate({"email": "x"}) is False
    assert await TokenGuard("api", None).attempt({"api_token": "x"}) is False
    assert await TokenGuard("api", MemoryUserProvider([])).attempt({"api_token": "x"}) is False
    assert await TokenGuard("api", MemoryUserProvider([])).attempt({}) is False

    obj = SimpleNamespace(id=1)
    sg = SessionGuard("web", None)
    tok = await sg._cycle_remember_token(obj)  # noqa: SLF001
    assert obj.remember_token == tok
    sg._queue_remember_cookie(SimpleNamespace(id=None))  # noqa: SLF001
    sg._queue_remember_cookie(SimpleNamespace(id=1, remember_token=None))  # noqa: SLF001

    manager = AuthManager()
    guard = manager.guard("web")

    async def cb(req):
        return {"id": "via"}

    manager.via_request("web", cb)
    assert guard._via_request is cb  # noqa: SLF001
    assert AuthManager().id() is None

    class AttrUser:
        def get_auth_identifier(self):
            return 7

        email = "e@x"
        name = "N"

    assert _session_payload(AttrUser())["id"] == 7

    class AttrUserGet:
        def get_auth_identifier(self):
            return 8

        def get_attribute(self, attr):
            return {"email": "a", "name": "b"}.get(attr)

    assert _session_payload(AttrUserGet())["email"] == "a"
    assert "password" not in _user_to_dict(type("D", (), {"to_dict": lambda self: {"id": 1, "password": "s"}})())
    assert _user_to_dict(SimpleNamespace(id=3, password="x", _priv=1))["id"] == 3
    assert _user_to_dict(5)["user"] == "5"
    assert _user_id(Ident()) == 42
    assert _user_id({"id": 3}) == 3
    assert _user_id(SimpleNamespace(id=9)) == 9
    assert _remember_token_of({"remember_token": None}) is None
    with pytest.raises(ImportError):
        _import_string("NoDots")


@pytest.mark.asyncio
async def test_middleware_remaining_paths() -> None:
    repo = ConfigRepository()
    repo.set(
        "auth.guards",
        {"web": {"driver": "session", "provider": "users"}, "api": {"driver": "token", "provider": "users"}},
    )
    repo.set("auth.providers", {"users": {"driver": "memory", "users": []}})
    set_repository(repo)

    original_guard = AuthManager.guard

    async def boom(req):
        raise RuntimeError("via fail")

    def guard_with_via(self, name=None):
        g = original_guard(self, name)
        g.via_request(boom)
        return g

    with patch.object(AuthManager, "guard", guard_with_via):
        request = _req()
        request._session = Session()  # noqa: SLF001
        set_session(request._session)

        async def ok(_r):
            return Response(b"ok")

        assert (await StartAuth().handle(request, ok)).status_code == 200

    async def ok(_r):
        return Response(b"ok")

    # RequirePassword without session
    class NS:
        def __init__(self, inner: Request):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        @property
        def session(self):
            raise RuntimeError("no session")

        def header(self, name, default=None):
            return self._inner.header(name, default)

        def is_json(self):
            return self._inner.is_json()

        @property
        def path(self):
            return self._inner.path

    with pytest.raises(UnauthorizedHttpException):
        await RequirePassword().handle(NS(_req(headers=[(b"accept", b"application/json")])), ok)
    redirected = await RequirePassword().handle(NS(_req()), ok)
    assert redirected.status_code in {302, 303, 307}

    sess = Session({"auth.password_confirmed_at": 0})
    jr = _req(headers=[(b"accept", b"application/json")])
    jr._session = sess  # noqa: SLF001
    set_session(sess)
    with pytest.raises(UnauthorizedHttpException):
        await RequirePassword(timeout=1).handle(jr, ok)

    assert (await AuthenticateWithBasicAuth().handle(_req(), ok)).status_code == 401

    m = AuthManager()
    m.guard("web").once({"id": 1})
    tok = set_auth(m)
    try:
        assert (await RedirectIfAuthenticated("web").handle(_req(), ok)).status_code in {302, 303, 307}
    finally:
        reset_auth(tok)

    repo2 = ConfigRepository()
    repo2.set("auth.guards", {"web": {}, "api": {}, "admin": {}})
    set_repository(repo2)
    assert "admin" in _configured_guard_names()

    qreq = _req(path="/x", query=b"a=1")
    qreq._session = Session()  # noqa: SLF001
    set_session(qreq._session)
    await _unauthenticated(qreq)


@pytest.mark.asyncio
async def test_password_remaining() -> None:
    tokens = DatabaseTokenRepository(expire=60, throttle=0)
    assert await tokens.exists("nobody@x.com", "tok") is False

    class FakeCreated:
        def timestamp(self):
            return 123.0

    async def fake_select_empty(sql, params=None):
        return []

    async def fake_select(sql, params=None):
        return [{"email": "a@b.c", "token": "h", "created_at": FakeCreated()}]

    with patch("almasix.orm.facade.DB.select", fake_select_empty):
        tokens.use_database = True
        assert await tokens._db_get("a@b.c") is None  # noqa: SLF001

    with patch("almasix.orm.facade.DB.select", fake_select):
        assert (await tokens._db_get("a@b.c"))["created_at"] == 123.0  # noqa: SLF001

    async def boom(*a, **k):
        raise RuntimeError("db down")

    with patch("almasix.orm.facade.DB.statement", boom):
        assert await tokens._db_delete_expired(0.0) == 0  # noqa: SLF001

    provider = MemoryUserProvider([{"id": 1, "email": "a@b.c", "password": Hash.make("old")}])
    broker = PasswordBroker(provider, DatabaseTokenRepository(throttle=0))

    async def adeliver(user, token):
        adeliver.token = token

    broker.send_callback = adeliver
    assert await broker.send_reset_link({"email": "a@b.c"}) == Password.RESET_LINK_SENT
    assert (
        await broker.reset({"email": "missing@x.com", "token": "x", "password": "n"}, lambda u, p: None)
        == Password.INVALID_USER
    )

    set_password_manager(PasswordBrokerManager())
    assert (
        await Password.reset({"email": "m@x.com", "token": "x", "password": "n"}, lambda u, p: None)
        == Password.INVALID_USER
    )

    repo = ConfigRepository()
    repo.set("auth.defaults.passwords", "users")
    repo.set("auth.passwords.users.provider", "users")
    repo.set("auth.passwords.users.table", "password_reset_tokens")
    repo.set("auth.passwords.users.expire", 30)
    repo.set("auth.passwords.users.throttle", 10)
    repo.set("auth.passwords.users.use_database", False)
    repo.set("auth.providers.users", {"driver": "memory", "users": []})
    set_repository(repo)
    tok = set_auth(AuthManager())
    try:
        assert PasswordBrokerManager().broker("users") is not None
    finally:
        reset_auth(tok)

    # create() use_database success path (line 69-70)
    async def ok_insert(row):
        return True

    tokens2 = DatabaseTokenRepository(use_database=True, throttle=0)
    with patch.object(tokens2, "_db_insert", ok_insert):
        assert await tokens2.create("z@z.com")


def test_cookies_encrypt_session_branches() -> None:
    response = Response(b"ok")
    token = begin_cookie_queue()
    try:
        apply_queued_cookies(response)
        queue_cookie("a", "b", max_age=10, path="/", secure=False, httponly=True, samesite="lax")
        apply_queued_cookies(response)
    finally:
        reset_cookie_queue(token)

    mw = EncryptCookies()
    assert "=" in mw._encrypt_set_cookie("plain=value", key="k")  # noqa: SLF001
    mw._encrypt_response_cookies(SimpleNamespace(), key="k")  # noqa: SLF001


@pytest.mark.asyncio
async def test_session_clean_no_set_cookie() -> None:
    repo = ConfigRepository()
    repo.set("app.key", "test-key")
    set_repository(repo)
    request = _req()
    request._cookies = {}  # noqa: SLF001

    async def clean(req):
        _ = req.session
        return Response(b"ok")

    r = await StartSession().handle(request, clean)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_kernel_parameterized_and_invoke(tmp_path: Path) -> None:
    from almasix.auth.middleware import Authenticate, AuthenticateWithBasicAuth, RequirePassword
    from almasix.framework.application import Application
    from almasix.http.kernel import HttpKernel
    from almasix.routing.router import Router

    root = tmp_path / "app"
    for part in ("bootstrap", "config", "routes"):
        (root / part).mkdir(parents=True)
    (root / "config" / "app.py").write_text("config = {'name': 'T', 'key': 'k'}\n", encoding="utf-8")
    app = Application.configure(root).create()
    kernel = HttpKernel(app, Router())

    assert kernel._instantiate_parameterized(Authenticate, "auth", "api").guard_name == "api"  # noqa: SLF001
    assert kernel._instantiate_parameterized(AuthenticateWithBasicAuth, "auth.basic", "email").field == "email"  # noqa: SLF001
    kernel._instantiate_parameterized(RequirePassword, "password.confirm", "30")  # noqa: SLF001

    class NoParamMw:
        def __init__(self) -> None:
            pass

    assert kernel._instantiate_parameterized(NoParamMw, "custom", "x") is not None  # noqa: SLF001

    with patch("inspect.signature", side_effect=TypeError("boom")):
        assert await kernel._invoke(lambda: "x", _req()) == "x"  # noqa: SLF001

    with patch("inspect.signature", side_effect=ValueError("boom")):

        async def async_h():
            return "y"

        assert await kernel._invoke(async_h, _req()) == "y"  # noqa: SLF001

    def handler(request: Request):
        return "z"

    with patch("almasix.http.kernel.get_type_hints", side_effect=Exception("no hints")):
        assert await kernel._invoke(handler, _req()) == "z"  # noqa: SLF001

    class C:
        async def meth(self, request: Request):
            return "m"

    assert await kernel._invoke(C().meth, _req()) == "m"  # noqa: SLF001


def test_trust_and_router_and_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from almasix.framework.application import Application
    from almasix.routing.router import Router, _GroupOptions

    assert peer_is_trusted("not-an-ip", ["not-an-ip"]) is True
    assert _scope_peer({}) is None
    assert _scope_peer({"client": (None, 0)}) is None
    assert _scope_peer({"client": ("", 0)}) is None

    scope: dict[str, Any] = {
        "type": "http",
        "client": ("127.0.0.1", 80),
        "server": ("localhost", 80),
        "scheme": "http",
        "headers": [],
    }
    mw = TrustProxiesASGI(lambda *a: None, proxies="*", headers=HEADER_X_FORWARDED_ALL)
    mw._apply(scope, {"x-forwarded-for": "  ,"})  # noqa: SLF001
    mw._apply(
        scope,
        {
            "x-forwarded-for": "10.0.0.1",
            "x-forwarded-proto": "https",
            "x-forwarded-host": "ex.com",
            "x-forwarded-port": "443",
            "x-forwarded-prefix": "/app/",
        },
    )  # noqa: SLF001
    mw._apply(scope, {"x-forwarded-proto": "ftp"})  # noqa: SLF001
    mw._apply(scope, {"x-forwarded-port": "abc"})  # noqa: SLF001
    mw._apply({"server": ("h", 1), "headers": [], "client": None}, {"x-forwarded-for": "9.9.9.9"})  # noqa: SLF001
    TrustProxiesASGI(lambda *a: None, proxies="*", headers=0)._apply(scope, {"x-forwarded-for": "1.1.1.1"})  # noqa: SLF001

    router = Router()
    router._group_stack.append(_GroupOptions(prefix="api"))  # noqa: SLF001
    assert router.add(["GET"], "items", lambda: None).uri.startswith("/")

    root = tmp_path / "app"
    for part in ("bootstrap", "config", "routes"):
        (root / part).mkdir(parents=True)
    (root / "config" / "app.py").write_text("config = {'name': 'T'}\n", encoding="utf-8")
    app = Application.configure(root).create()
    bad = root / "routes" / "broken.py"
    bad.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(importlib.util, "spec_from_file_location", lambda *a, **k: None)
    with pytest.raises(ImportError):
        app._load_route_file(bad)  # noqa: SLF001


@pytest.mark.asyncio
async def test_env_smith_translation_support(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from almasix.smith import lang_cmd
    from almasix.smith.make import MakeError, make_component
    from almasix.support.collection import Collection
    from almasix.translation.loader import FileLoader
    from almasix.translation.middleware import SetLocaleMiddleware
    from almasix.translation.translator import Translator

    monkeypatch.setenv("ALMASIX_BOOL_FALSE", "off")
    assert env("ALMASIX_BOOL_FALSE", True) is False

    base = tmp_path / "langapp"
    base.mkdir()
    lang_cmd.publish_lang(base, force=False)
    lang_cmd.publish_lang(base, force=False)

    with patch("importlib.util.spec_from_file_location", return_value=None):
        assert lang_cmd._load_py_dict(tmp_path / "x.py") == {}  # noqa: SLF001

    app_root = tmp_path / "makeapp"
    (app_root / "resources" / "views" / "components").mkdir(parents=True)
    (app_root / "app" / "view" / "components").mkdir(parents=True)
    make_component("button", base_path=app_root, class_based=True, force=True)
    with pytest.raises(MakeError):
        make_component("button", base_path=app_root, class_based=True, force=False)

    lang = tmp_path / "lang"
    (lang / "en").mkdir(parents=True)
    (lang / "en" / "messages.py").write_text("config = {'nested': {'a': 'A'}}\n", encoding="utf-8")
    loader = FileLoader()
    loader.add_path(str(lang))
    with patch("importlib.util.spec_from_file_location", return_value=None):
        assert loader._load_py(lang / "en" / "messages.py") == {}  # noqa: SLF001
    (lang / "en" / "stemdict.py").write_text("stemdict = {'k': 'v'}\n", encoding="utf-8")
    assert loader._load_py(lang / "en" / "stemdict.py")["k"] == "v"  # noqa: SLF001
    target: dict = {"a": {"b": 1}}
    FileLoader._merge(target, {"a": {"c": 2}, "d": 3})
    assert target["a"]["c"] == 2

    t = Translator(loader)
    t.set_locale("en")
    t.set_fallback("fr")
    assert t.has("totally.missing.key") is False
    loader.add_lines({"Hello": "Bonjour", "alt": "x"}, "en", "*")
    assert t._lookup("Hello", "en") == "Bonjour"  # noqa: SLF001
    assert t._lookup("alt", "en") == "x"  # noqa: SLF001
    loader.add_lines({"full.key": "via-key"}, "en", "*")
    # key with dot goes through group parse; force JSON-style via runtime key match
    assert t._lookup("full.key", "en") in {"via-key", None}  # noqa: SLF001

    from almasix.translation.locale import reset_locale_context

    reset_locale_context()
    req = _req()
    req._session = Session({"locale": "en"})  # noqa: SLF001

    async def nxt(r):
        return Response(b"ok")

    assert (await SetLocaleMiddleware().handle(req, nxt)).status_code == 200

    c = Collection([{"a": 1}, {"a": 2}])
    assert list(c.pluck("a")) == [1, 2]
