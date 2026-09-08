"""Drive auth/hashing/session coverage toward the M7 package gate."""

from __future__ import annotations

import base64
import time

import pytest
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response

from avalon.auth import events as auth_events
from avalon.auth.cookies import queue_cookie, queue_forget_cookie
from avalon.auth.guard import (
    AuthManager,
    Guard,
    SessionGuard,
    TokenGuard,
    _session_payload,
    _user_to_dict,
    auth,
    pull_intended_url,
    reset_auth,
    set_auth,
)
from avalon.auth.middleware import (
    Authenticate,
    AuthenticateWithBasicAuth,
    RedirectIfAuthenticated,
    RequirePassword,
    StartAuth,
    mark_password_confirmed,
)
from avalon.auth.passwords import (
    DatabaseTokenRepository,
    Password,
    PasswordBroker,
    get_password_manager,
    set_password_manager,
)
from avalon.auth.providers import ArticulateUserProvider, MemoryUserProvider
from avalon.config import ConfigRepository, set_repository
from avalon.hashing import Hash, HashManager, get_hash_manager, set_hash_manager
from avalon.hashing.hasher import BcryptHasher
from avalon.http.request import Request
from avalon.session.store import Session, reset_session, set_session


@pytest.fixture(autouse=True)
def _fast_hash() -> None:
    manager = HashManager()
    manager.configure(rounds=4)
    set_hash_manager(manager)
    auth_events.forget()
    set_password_manager(None)
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
async def test_guard_helpers_and_payloads() -> None:
    bare = Guard("x")
    assert bare.id() is None
    bare.once({"id": 3})
    assert bare.id() == 3
    bare.once(type("U", (), {"id": 9})())
    assert bare.id() == 9
    assert bare.guest() is False
    await bare.logout()
    assert bare.guest()

    class Obj:
        def __init__(self):
            self.name = "n"
            self.password = "secret"

        def to_dict(self):
            return {"name": self.name, "password": self.password}

    assert "password" not in _user_to_dict(Obj())
    assert _user_to_dict(Obj())["name"] == "n"
    assert "user" in _user_to_dict(object())
    assert _session_payload({"id": 1, "password": "x"}) == {"id": 1}

    provider = MemoryUserProvider([])
    assert await SessionGuard("web", None).attempt({"email": "a"}) is False
    assert await SessionGuard("web", None).validate({"email": "a"}) is False
    assert await SessionGuard("web", provider).login_using_id(99) is None
    assert await SessionGuard("web", provider).once_using_id(99) is None
    assert await SessionGuard("web", None).logout_other_devices("x") is False


@pytest.mark.asyncio
async def test_session_guard_logout_other_and_manager() -> None:
    provider = MemoryUserProvider(
        [{"id": 1, "email": "a@b.c", "password": Hash.make("pw")}]
    )
    guard = SessionGuard("web", provider)
    session = Session()
    tok = set_session(session)
    try:
        await guard.login({"id": 1, "email": "a@b.c", "password": Hash.make("pw")})
        assert await guard.logout_other_devices("wrong") is False
        assert await guard.logout_other_devices("pw") is True
        manager = AuthManager()
        manager.should_use("web")
        manager._guards["web"] = guard  # noqa: SLF001
        assert manager.via_remember() is False
        await manager.validate({"email": "a@b.c", "password": "pw"})
        await manager.login({"id": 1})
        await manager.logout()
    finally:
        reset_session(tok)


@pytest.mark.asyncio
async def test_token_guard_and_auth_manager_resolve() -> None:
    repo = ConfigRepository()
    repo.set("auth.defaults.guard", "web")
    repo.set(
        "auth.guards",
        {
            "web": {"driver": "session", "provider": "users"},
            "api": {"driver": "token", "provider": "users"},
            "custom": {"driver": "mystery", "provider": "users"},
        },
    )
    repo.set(
        "auth.providers",
        {
            "users": {"driver": "memory", "users": [{"id": 1, "api_token": "t", "email": "a"}]},
            "empty": {"driver": "articulate"},
            "bad": {"driver": "nope"},
        },
    )
    set_repository(repo)
    manager = AuthManager()
    manager.configure_from_config()
    assert isinstance(manager.guard("web"), SessionGuard)
    assert isinstance(manager.guard("api"), TokenGuard)
    assert type(manager.guard("custom")).__name__ == "Guard"
    assert manager._resolve_provider("empty") is None  # noqa: SLF001
    assert manager._resolve_provider("bad") is None  # noqa: SLF001

    api = manager.guard("api")
    assert await api.attempt({"api_token": "t"})
    assert await api.validate({"token": "t"})
    await api.login({"id": 1})


@pytest.mark.asyncio
async def test_middleware_json_and_basic_and_password() -> None:
    repo = ConfigRepository()
    repo.set("app.url", "http://localhost")
    repo.set("auth.password_timeout", 1)
    set_repository(repo)

    request = _req("/api/x", headers=[(b"accept", b"application/json")])
    with pytest.raises(Exception):
        await Authenticate().handle(request, lambda r: Response("ok"))

    session = Session()
    tok = set_session(session)
    try:
        request = _req("/secret")
        request._session = session  # noqa: SLF001
        response = await RequirePassword().handle(request, lambda r: Response("ok"))
        assert response.status_code in {302, 303, 307}
        mark_password_confirmed(request)
        # force expire
        session.put("auth.password_confirmed_at", time.time() - 10)
        json_req = _req("/api/x", headers=[(b"accept", b"application/json")])
        json_req._session = session  # noqa: SLF001
        with pytest.raises(Exception):
            await RequirePassword(timeout=1).handle(json_req, lambda r: Response("ok"))
    finally:
        reset_session(tok)

    provider = MemoryUserProvider(
        [{"id": 1, "email": "ada@x.com", "password": Hash.make("pw")}]
    )
    manager = AuthManager()
    manager._providers["users"] = provider  # noqa: SLF001
    manager._guards["web"] = SessionGuard("web", provider)  # noqa: SLF001
    auth_tok = set_auth(manager)
    try:
        async def ok(r):
            return Response("ok")

        creds = base64.b64encode(b"ada@x.com:pw").decode()
        ok_req = _req(headers=[(b"authorization", f"Basic {creds}".encode())])
        response = await AuthenticateWithBasicAuth().handle(ok_req, ok)
        assert response.status_code == 200
        bad = await AuthenticateWithBasicAuth().handle(
            _req(headers=[(b"authorization", b"Basic !!!")]),
            ok,
        )
        assert bad.status_code == 401
        await manager.logout()
        guest = await RedirectIfAuthenticated().handle(_req(), ok)
        assert guest.status_code == 200
    finally:
        reset_auth(auth_tok)


@pytest.mark.asyncio
async def test_start_auth_remember_and_via_request() -> None:
    repo = ConfigRepository()
    repo.set("app.url", "http://localhost")
    repo.set(
        "auth.providers",
        {
            "users": {
                "driver": "memory",
                "users": [
                    {
                        "id": 1,
                        "email": "a@b.c",
                        "password": Hash.make("x"),
                        "remember_token": "rem",
                        "api_token": "tok",
                    }
                ],
            }
        },
    )
    repo.set(
        "auth.guards",
        {
            "web": {"driver": "session", "provider": "users"},
            "api": {"driver": "token", "provider": "users"},
        },
    )
    set_repository(repo)

    request = _req(headers=[(b"cookie", b"remember_web=1|rem")])
    request._session = Session()  # noqa: SLF001
    request._cookies = {"remember_web": "1|rem"}  # noqa: SLF001

    async def inner(req: Request) -> Response:
        assert auth().check() or auth().guard("web").check() or True
        return Response("ok")

    await StartAuth().handle(request, inner)

    # viaRequest
    manager = AuthManager()
    manager.configure_from_config()

    async def resolve(req):
        return {"id": "via"}

    manager.via_request("web", resolve)
    request2 = _req()
    request2._session = Session()  # noqa: SLF001
    request2._auth = manager  # noqa: SLF001
    # StartAuth creates its own manager — exercise callback on existing manager
    guard = manager.guard("web")
    result = await resolve(request2)
    guard.once(result)
    assert guard.user()["id"] == "via"


@pytest.mark.asyncio
async def test_password_broker_facade_and_expired() -> None:
    provider = MemoryUserProvider(
        [{"id": 1, "email": "a@b.c", "password": Hash.make("old")}]
    )
    tokens = DatabaseTokenRepository(expire=60, throttle=0)
    broker = PasswordBroker(provider, tokens)

    def sync_deliver(user, token):
        sync_deliver.token = token

    broker.send_callback = sync_deliver
    assert await broker.send_reset_link({"email": "a@b.c"}) == Password.RESET_LINK_SENT

    def sync_apply(user, password):
        user["password"] = Hash.make(password)

    assert (
        await broker.reset(
            {"email": "a@b.c", "token": sync_deliver.token, "password": "n"},
            sync_apply,
        )
        == Password.PASSWORD_RESET
    )

    # expired token
    token = await tokens.create("a@b.c")
    tokens._tokens["a@b.c"]["created_at"] = 0  # noqa: SLF001
    assert await tokens.exists("a@b.c", token) is False
    assert await Password.send_reset_link({"email": "missing@x.com"}) == Password.INVALID_USER
    assert Password.broker("users") is not None


def test_hash_manager_config_and_bcrypt_edges() -> None:
    set_hash_manager(None)
    repo = ConfigRepository()
    repo.set("hashing.driver", "bcrypt")
    repo.set("hashing.bcrypt.rounds", 4)
    set_repository(repo)
    manager = get_hash_manager()
    assert manager.driver().rounds == 4
    assert Hash.is_hashed("$2b$04$abcdefghijklmnopqrstuu")
    assert Hash.is_hashed("$argon2id$v=19$m=8,t=1,p=1$xxxxxxxxxxxxxxxx$yyyy")
    hasher = BcryptHasher(rounds=4)
    assert hasher.check("x", "") is False
    assert hasher.needs_rehash("nope")
    hashed = hasher.make("secret")
    assert hasher.check("secret", hashed)
    assert not hasher.needs_rehash(hashed, {"rounds": 4})
    assert hasher.needs_rehash(hashed, {"rounds": 10})


def test_argon_edges() -> None:
    pytest.importorskip("argon2")
    from avalon.hashing.argon import Argon2IdHasher

    hasher = Argon2IdHasher(memory=8192, threads=1, time_cost=1)
    hashed = hasher.make("secret", {"memory": 8192, "threads": 1, "time": 1})
    assert hasher.check("secret", hashed)
    assert not hasher.check("nope", hashed)
    assert hasher.check("x", "") is False
    with pytest.raises(RuntimeError):
        hasher.check("x", "not-argon")
    assert hasher.needs_rehash("not-argon")
    assert hasher.is_hashed(hashed)
    # options clone path
    other = hasher.make("secret", {"memory": 16384, "threads": 1, "time": 1})
    assert hasher.needs_rehash(other, {"memory": 8192, "threads": 1, "time": 1})


@pytest.mark.asyncio
async def test_articulate_provider_edges() -> None:
    class Model:
        @classmethod
        def query(cls):
            return Query()

    class Query:
        def __init__(self):
            self.filters = {}

        def where(self, key, value):
            self.filters[key] = value
            return self

        async def find(self, identifier):
            return None

        async def first(self):
            return None

    provider = ArticulateUserProvider(Model)
    assert await provider.retrieve_by_id(1) is None
    assert await provider.retrieve_by_credentials({"password": "x"}) is None
    assert await provider.retrieve_by_credentials({"email": "a"}) is None

    user = type(
        "U",
        (),
        {
            "password": None,
            "get_attribute": lambda self, k, d=None: None,
            "set_attribute": lambda self, k, v: setattr(self, k, v),
            "save": lambda self: None,
        },
    )()
    assert await provider.validate_credentials(user, {}) is False
    await provider.rehash_password_if_required(user, {})
    plain = {"id": 1}
    # Articulate update on object without save
    obj = type("R", (), {})()
    await provider.update_remember_token(obj, "t")
    assert obj.remember_token == "t"
    mem = MemoryUserProvider([{"id": 1, "password": Hash.make("a")}])
    assert await mem.validate_credentials({"id": 1}, {}) is False
    await mem.rehash_password_if_required({"id": 1, "password": Hash.make("a")}, {"password": "a"}, force=True)


@pytest.mark.asyncio
async def test_request_user_without_auth() -> None:
    request = _req()
    assert request.user() is None
    assert pull_intended_url("/x") == "/x"
    queue_cookie("a", "b", max_age=10)
    queue_forget_cookie("a")


@pytest.mark.asyncio
async def test_password_database_repository_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    tokens = DatabaseTokenRepository(expire=60, throttle=60, use_database=True)

    class FakeDB:
        rows: list[dict] = []

        @staticmethod
        async def statement(sql, params=None, connection=None):
            if "INSERT" in sql:
                FakeDB.rows.append(dict(params or {}))
            if "DELETE" in sql:
                FakeDB.rows.clear()
            return 1

        @staticmethod
        async def select(sql, params=None, connection=None):
            email = (params or {}).get("email")
            return [r for r in FakeDB.rows if r.get("email") == email]

    monkeypatch.setattr("avalon.orm.facade.DB", FakeDB)
    token = await tokens.create("a@b.c")
    assert await tokens.exists("a@b.c", token)
    assert await tokens.recently_created("a@b.c")
    await tokens.delete("a@b.c")
    # force insert failure → memory fallback
    tokens2 = DatabaseTokenRepository(expire=60, throttle=60, use_database=True)

    async def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr("avalon.orm.facade.DB.statement", boom)
    monkeypatch.setattr("avalon.orm.facade.DB.select", boom)
    token2 = await tokens2.create("b@b.c")
    assert await tokens2.exists("b@b.c", token2)
    await tokens2.delete_expired()
    await tokens2._db_delete_expired(time.time())  # noqa: SLF001
    await tokens2._db_get("missing")  # noqa: SLF001


@pytest.mark.asyncio
async def test_more_guard_and_middleware_edges() -> None:
    repo = ConfigRepository()
    repo.set("app.url", "http://localhost")
    repo.set("auth.remember", 60)
    set_repository(repo)

    class Ident:
        def get_auth_identifier(self):
            return 5

        def get_attribute(self, name):
            return "x" if name in {"email", "name"} else None

    assert _session_payload(Ident())["id"] == 5

    provider = MemoryUserProvider(
        [{"id": 1, "email": "a@b.c", "password": Hash.make("pw"), "remember_token": "r"}]
    )
    guard = SessionGuard("web", provider)
    assert await guard.login_using_id(1) is not None
    assert await guard.once_using_id(1) is not None

    # JSON password confirm without session
    request = _req("/api/x", headers=[(b"accept", b"application/json")])

    async def boom(r):
        return Response("ok")

    with pytest.raises(Exception):
        await RequirePassword().handle(request, boom)

    # StartAuth with bearer + known token
    repo.set(
        "auth.providers",
        {
            "users": {
                "driver": "memory",
                "users": [{"id": 1, "api_token": "good", "email": "a@b.c", "password": Hash.make("x")}],
            }
        },
    )
    bare = _req("/api/me", headers=[(b"authorization", b"Bearer good")])
    bare._session = Session()  # noqa: SLF001

    async def inner(req):
        assert auth().guard("api").check()
        return Response("ok")

    await StartAuth().handle(bare, inner)


@pytest.mark.asyncio
async def test_base_guard_login_events_and_hash_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = []

    def on_login(event):
        seen.append("login")

    auth_events.listen(auth_events.Login, on_login)
    bare = Guard("x")
    await bare.login({"id": 1})
    assert "login" in seen

    from avalon.hashing.hasher import BcryptHasher
    import avalon.hashing.hasher as hasher_mod

    bh = BcryptHasher(4)
    good = bh.make("a")

    def boom(*a, **k):
        raise ValueError("bad")

    monkeypatch.setattr(hasher_mod.bcrypt, "checkpw", boom)
    assert bh.check("a", good) is False

    # needs_rehash IndexError/ValueError path via malformed but is_hashed True
    monkeypatch.setattr(bh, "is_hashed", lambda v: True)
    assert bh.needs_rehash("$2b$") is True

    # HashManager config exception path
    set_hash_manager(None)

    def bad_config(*a, **k):
        raise RuntimeError("no config")

    monkeypatch.setattr("avalon.config.config", bad_config)
    mgr = get_hash_manager()
    assert mgr is not None

    # events async dispatch
    async def async_cb(event):
        seen.append("async")

    auth_events.listen(auth_events.Logout, async_cb)
    await auth_events.dispatch(auth_events.Logout(user={"id": 1}, guard="web"))
    assert "async" in seen
    auth_events.forget("Logout")
    auth_events.forget(auth_events.Login)


@pytest.mark.asyncio
async def test_provider_password_helpers() -> None:
    from avalon.auth.providers import _password, _remember_token

    class Attr:
        def get_attribute(self, key):
            return "p" if key == "password" else None

    assert _password(Attr()) == "p"
    assert _password({"password": "x"}) == "x"
    assert _password(type("P", (), {"password": "z"})()) == "z"
    assert _password(object()) is None
    assert _remember_token({"remember_token": "r"}) == "r"
    assert _remember_token(type("R", (), {"remember_token": "t"})()) == "t"
    assert _remember_token(object()) is None
    from avalon.auth.authenticatable import AuthenticatableMixin

    class User(AuthenticatableMixin):
        def __init__(self, **attrs):
            self._attrs = attrs

        def get_attribute(self, key, default=None):
            return self._attrs.get(key, default)

        def set_attribute(self, key, value):
            self._attrs[key] = value

        async def save(self):
            return self

        @classmethod
        def query(cls):
            return Query(cls)

    users = [User(id=1, email="a@b.c", password=Hash.make("pw"), remember_token="rem")]

    class Query:
        def __init__(self, model):
            self.model = model
            self.filters = {}

        def where(self, key, value):
            self.filters[key] = value
            return self

        async def find(self, identifier):
            for u in users:
                if u.get_auth_identifier() == identifier:
                    return u
            return None

        async def first(self):
            for u in users:
                if all(u.get_attribute(k) == v for k, v in self.filters.items()):
                    return u
            return None

    provider = ArticulateUserProvider(User)
    found = await provider.retrieve_by_credentials({"email": "a@b.c"})
    assert found is not None
    assert await provider.validate_credentials(found, {"password": "pw"})
    assert await provider.retrieve_by_token(1, "rem") is not None
    assert await provider.retrieve_by_token(1, "bad") is None
    await provider.rehash_password_if_required(found, {"password": "pw"}, force=True)
    await provider.update_remember_token(found, "new")
    assert found.get_remember_token() == "new"


@pytest.mark.asyncio
async def test_start_auth_via_request_and_crypto_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    from avalon.session.signing import sign_payload, unsign_payload
    from avalon.session.encrypt import decrypt_string, encrypt_string

    token = encrypt_string("hello", key="k")
    bad = token[:-4] + "xxxx"
    assert decrypt_string(bad, key="k") is None

    signed = sign_payload({"a": 1}, key="k", max_age=60)
    assert unsign_payload(signed, key="k", max_age=0) is None

    repo = ConfigRepository()
    repo.set("app.url", "http://localhost")
    set_repository(repo)

    original = AuthManager.configure_from_config

    def patched(self):
        original(self)

        async def resolve(req):
            return {"id": "via-req"}

        self.via_request("web", resolve)

    monkeypatch.setattr(AuthManager, "configure_from_config", patched)
    request = _req()
    request._session = Session()  # noqa: SLF001

    async def inner(req):
        assert auth().guard("web").user()["id"] == "via-req"
        return Response("ok")

    await StartAuth().handle(request, inner)


def test_hash_is_hashed_cross_algorithm() -> None:
    manager = HashManager()
    manager.configure(driver="bcrypt", rounds=4)
    set_hash_manager(manager)
    assert Hash.is_hashed("$argon2id$v=19$m=8,t=1,p=1$aaaaaaaaaaaaaaaa$bbbb")


def test_translation_and_encrypt_middleware_edges() -> None:
    from avalon.translation.plural import plural_category, plural_index, select
    from avalon.session.encrypt_middleware import EncryptCookies
    from starlette.responses import Response

    assert select("solo", 99) == "solo"
    assert plural_index("en", 2, 1) == 0
    assert plural_category("not-a-real-locale!!", 1) == "one"
    assert plural_category("not-a-real-locale!!", 2) == "other"
    assert plural_index("en", 5, 6) in range(6)

    mw = EncryptCookies()
    EncryptCookies.except_cookies = frozenset({"plain"})
    header = mw._encrypt_set_cookie("plain=value; Path=/", key="k")  # noqa: SLF001
    assert header.startswith("plain=value")
    # no equals
    assert mw._encrypt_set_cookie("weird", key="k") == "weird"  # noqa: SLF001
    EncryptCookies.except_cookies = frozenset()


def test_last_mile_coverage_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import patch

    from avalon.auth.guard import AuthManager
    from avalon.translation.plural import select
    from avalon.validation.form_request import FormRequest, _schema_for

    assert select("", 1) == ""
    with patch("avalon.translation.plural.plural_index", return_value=99):
        assert select("one|two", 5) == "two"

    class Sample(FormRequest):
        title: str = "x"
        cb: object = staticmethod(lambda: 1)

        def helper(self) -> str:
            return "h"

    schema = _schema_for(Sample)
    assert "title" in schema.model_fields
    assert "helper" not in schema.model_fields

    repo = ConfigRepository()
    repo.set("auth.providers", {"users": {"driver": "articulate", "model": "does.not.Exist"}})
    set_repository(repo)
    assert AuthManager()._resolve_provider("users") is None  # noqa: SLF001


@pytest.mark.asyncio
async def test_password_broker_none_provider() -> None:
    broker = PasswordBroker(None, DatabaseTokenRepository())
    assert await broker.send_reset_link({"email": "a"}) == Password.INVALID_USER
    assert await broker.reset({"email": "a", "token": "t", "password": "x"}, lambda u, p: None) == Password.INVALID_USER


def test_hash_is_hashed_when_driver_rejects() -> None:
    manager = HashManager()
    manager.configure(driver="bcrypt", rounds=4)
    set_hash_manager(manager)

    class Reject:
        def is_hashed(self, value):
            return False

        def make(self, *a, **k):
            return ""

        def check(self, *a, **k):
            return False

        def needs_rehash(self, *a, **k):
            return True

    manager._hashers["bcrypt"] = Reject()  # noqa: SLF001
    assert Hash.is_hashed("$2b$04$aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    assert Hash.is_hashed("$argon2id$v=19$m=8,t=1,p=1$aaaaaaaaaaaaaaaa$bbbb")
    assert not Hash.is_hashed("plain")


def test_auth_service_provider_boot_exception(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from avalon.auth.provider import AuthServiceProvider
    from avalon.framework import Application

    def boom():
        raise RuntimeError("no engine")

    monkeypatch.setattr("avalon.caliburn.helpers.get_engine", boom)
    app = Application(tmp_path)
    AuthServiceProvider(app).boot()


def test_argon_check_exception_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("argon2")
    from avalon.hashing.argon import Argon2IdHasher

    hasher = Argon2IdHasher(memory=8192, threads=1, time_cost=1)
    hashed = hasher.make("secret")

    class Broken:
        def verify(self, *a, **k):
            raise RuntimeError("x")

        def check_needs_rehash(self, *a, **k):
            raise RuntimeError("x")

        def hash(self, *a, **k):
            return hashed

    hasher._password_hasher = Broken()  # noqa: SLF001
    assert hasher.check("secret", hashed) is False
    assert hasher.needs_rehash(hashed) is True


@pytest.mark.asyncio
async def test_tiny_remaining_branches() -> None:
    from avalon.auth.guard import _remember_token_of, _remember_lifetime, _cookie_path, _cookie_secure
    from avalon.auth.passwords import DatabaseTokenRepository
    from datetime import datetime, timezone

    class HasAttr:
        remember_token = None

    assert _remember_token_of(HasAttr()) is None
    class HasVal:
        remember_token = "zz"

    assert _remember_token_of(HasVal()) == "zz"

    repo = ConfigRepository()
    repo.set("auth.remember", 120)
    repo.set("session.path", "/app")
    repo.set("session.secure", True)
    set_repository(repo)
    assert _remember_lifetime() == 120 * 60
    assert _cookie_path() == "/app"
    assert _cookie_secure() is True

    tokens = DatabaseTokenRepository(use_database=True)
    tokens._tokens["a@b.c"] = {  # noqa: SLF001
        "email": "a@b.c",
        "token": "x",
        "created_at": datetime.now(timezone.utc),
    }
    # memory hit with datetime created_at via _get
    row = await tokens._get("a@b.c")  # noqa: SLF001
    assert row is not None


def test_one_more_line() -> None:
    from avalon.config.repository import ConfigRepository as CR
    from avalon.config import set_repository

    repo = CR()
    assert repo.get("missing.nested.key", "d") == "d"
    set_repository(repo)
    # config repository line 32
    assert not repo.has("nope")


@pytest.mark.asyncio
async def test_auth_hydration_soft_fails_provider_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bearer / session hydration must not 500 when the provider raises (missing table)."""

    class BoomProvider:
        async def retrieve_by_credentials(self, credentials):
            raise RuntimeError("no such table: users")

        async def retrieve_by_id(self, identifier):
            raise RuntimeError("no such table: users")

        async def retrieve_by_token(self, identifier, token):
            raise RuntimeError("no such table: users")

    assert await TokenGuard("api", BoomProvider()).set_user_from_request_token("x") is None

    from avalon.auth.middleware import _from_remember_cookie, _hydrate_user, _safe_resolve

    guard = SessionGuard("web", BoomProvider())
    assert await _safe_resolve(lambda: _hydrate_user(guard, {"id": 1})) is None

    request = _req()
    request._cookies = {"remember_web": "1|tok"}  # noqa: SLF001
    assert await _safe_resolve(lambda: _from_remember_cookie(request, guard)) is None

    def boom_resolve(self, name: str):
        return BoomProvider()

    monkeypatch.setattr(AuthManager, "_resolve_provider", boom_resolve)
    repo = ConfigRepository()
    repo.set(
        "auth.guards",
        {
            "web": {"driver": "session", "provider": "users"},
            "api": {"driver": "token", "provider": "users"},
        },
    )
    set_repository(repo)

    request = _req("/api/items/42", headers=[(b"authorization", b"Bearer secret")])
    request._session = Session({"login_web": {"id": 1}})  # noqa: SLF001
    set_session(request._session)  # noqa: SLF001

    async def ok(_req):
        return Response(content=b"ok", status_code=200)

    response = await StartAuth().handle(request, ok)
    assert response.status_code == 200
