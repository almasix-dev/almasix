"""M35 — RateLimiter façade, throttle middleware, and login throttling."""

from __future__ import annotations

import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request as StarletteRequest

from almasix.auth import LoginRateLimiter, attempt_login
from almasix.framework import Application
from almasix.http import Limit, RateLimiter, ThrottleRequests
from almasix.http.exceptions import TooManyRequestsHttpException
from almasix.http.rate_limiting import parse_rate
from almasix.http.request import Request
from tests.support import purge_generated_app_modules


def _write(root: Path, relative: str, body: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")


@pytest.fixture(autouse=True)
def _clean_limiter() -> Iterator[None]:
    RateLimiter.clear_limiters()
    yield
    RateLimiter.clear_limiters()


@pytest.fixture()
def app_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    purge_generated_app_modules()
    _write(tmp_path, ".env", "APP_NAME=RateApp\nAPP_DEBUG=true\nCACHE_STORE=array\n")
    for package in ("app", "app/http", "app/http/controllers", "app/providers"):
        _write(tmp_path, f"{package}/__init__.py", "")
    _write(
        tmp_path,
        "config/app.py",
        'config = {"name": "RateApp", "debug": True, "url": "http://testserver", '
        '"providers": ["app.providers.app_service_provider.AppServiceProvider"]}\n',
    )
    _write(
        tmp_path,
        "config/http.py",
        "config = {'middleware': [], 'middleware_groups': {'web': [], 'api': []}, "
        "'middleware_aliases': {}}\n",
    )
    _write(
        tmp_path,
        "config/cache.py",
        "config = {'default': 'array', 'limiter': None, 'prefix': 't_', "
        "'stores': {'array': {'driver': 'array'}}}\n",
    )
    _write(
        tmp_path,
        "app/providers/app_service_provider.py",
        """
        from starlette.responses import JSONResponse
        from almasix.http import Limit, RateLimiter
        from almasix.providers import ServiceProvider

        class AppServiceProvider(ServiceProvider):
            def register(self):
                pass

            def boot(self):
                RateLimiter.for_(
                    "api",
                    lambda request: Limit.per_minute(60).by(
                        request.ip() or "0.0.0.0"
                    ),
                )
                RateLimiter.for_(
                    "uploads",
                    lambda request: Limit.per_minute(2).by("uploads"),
                )
                RateLimiter.for_(
                    "vip",
                    lambda request: Limit.none(),
                )
                RateLimiter.for_(
                    "not-found",
                    lambda request: Limit.per_minute(1)
                    .by("nf")
                    .after(lambda response: getattr(response, "status_code", 0) == 404),
                )
                RateLimiter.for_(
                    "custom",
                    lambda request: Limit.per_minute(1)
                    .by("custom")
                    .response(
                        lambda req, headers: JSONResponse(
                            {"blocked": True}, status_code=429, headers=headers
                        )
                    ),
                )
        """,
    )
    _write(
        tmp_path,
        "bootstrap/app.py",
        """
        from pathlib import Path
        from almasix.framework import Application, Middleware

        BASE_PATH = Path(__file__).resolve().parent.parent


        def configure(middleware: Middleware) -> None:
            middleware.throttle_api()


        application = (
            Application.configure(BASE_PATH).with_middleware(configure).create()
        )
        asgi = application.asgi
        """,
    )
    _write(
        tmp_path,
        "routes/web.py",
        """
        from almasix.http.exceptions import NotFoundHttpException
        from almasix.routing import Route

        def _raise_not_found():
            raise NotFoundHttpException("gone")

        Route.get("/", lambda: {"ok": True}, name="home")
        with Route.group(prefix="/api", middleware=["api"]):
            Route.get("/ping", lambda: {"pong": True})
        Route.get("/burst", lambda: {"ok": True}, middleware=["throttle:2,1"])
        Route.get("/uploads", lambda: {"ok": True}, middleware=["throttle:uploads"])
        Route.get("/vip", lambda: {"ok": True}, middleware=["throttle:vip"])
        Route.get(
            "/missing-thing",
            _raise_not_found,
            middleware=["throttle:not-found"],
        )
        Route.get("/found-thing", lambda: {"here": True}, middleware=["throttle:not-found"])
        Route.get("/custom", lambda: {"ok": True}, middleware=["throttle:custom"])
        Route.get("/guest-auth", lambda: {"ok": True}, middleware=["throttle:2|5"])
        """,
    )
    (tmp_path / "storage" / "framework").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    sys.path.insert(0, str(tmp_path))
    try:
        yield tmp_path
    finally:
        purge_generated_app_modules()
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))


@pytest.fixture()
def client(app_dir: Path) -> Iterator[TestClient]:
    # Drive `throttle_api()` through Application.configure — do not import
    # `bootstrap.app` (that module name is shared across temp apps in the suite).
    from almasix.framework import Middleware

    def configure(middleware: Middleware) -> None:
        middleware.throttle_api()

    application = Application.configure(app_dir).with_middleware(configure).create()
    with TestClient(application.asgi) as test_client:
        yield test_client


def _fake_request(*, email: str = "a@b.c", ip: str = "10.0.0.1") -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/login",
        "raw_path": b"/login",
        "query_string": b"",
        "headers": [],
        "client": (ip, 12345),
        "server": ("test", 80),
    }
    request = Request(StarletteRequest(scope))
    request._input = {"email": email, "password": "x"}
    return request


# --- RateLimiter façade -----------------------------------------------------


def test_attempt_blocks_after_max(app_dir: Path) -> None:
    Application(app_dir).bootstrap()
    key = "send:1"
    RateLimiter.clear(key)
    assert RateLimiter.attempt(key, 2, lambda: "a") == "a"
    assert RateLimiter.attempt(key, 2, lambda: "b") == "b"
    assert RateLimiter.attempt(key, 2, lambda: "c") is False
    assert RateLimiter.attempts(key) == 2
    assert RateLimiter.remaining(key, 2) == 0
    assert RateLimiter.available_in(key) > 0
    RateLimiter.clear(key)
    assert RateLimiter.attempts(key) == 0


def test_increment_amount_and_aliases(app_dir: Path) -> None:
    Application(app_dir).bootstrap()
    key = "bump"
    RateLimiter.clear(key)
    assert RateLimiter.increment(key, decay_seconds=30, amount=3) == 3
    assert RateLimiter.hit(key, decay_seconds=30) == 4
    assert RateLimiter.tooManyAttempts(key, 4) is True  # type: ignore[attr-defined]
    RateLimiter.resetAttempts(key)  # type: ignore[attr-defined]
    assert RateLimiter.attempts(key) == 0
    assert RateLimiter.availableIn(key) > 0  # type: ignore[attr-defined]


def test_parse_rate_shapes() -> None:
    assert parse_rate("60,1") == (60, 60)
    assert parse_rate("10,0.5") == (10, 30)
    assert parse_rate("5") == (5, 60)


def test_limit_factories() -> None:
    assert Limit.per_second(1).decay_seconds == 1
    assert Limit.per_minute(2).max_attempts == 2
    assert Limit.per_hour(3).decay_seconds == 3600
    assert Limit.per_day(4).decay_seconds == 86400
    assert Limit.none().is_unlimited


def test_named_limiter_registration(app_dir: Path) -> None:
    Application(app_dir).bootstrap()
    assert RateLimiter.limiter("api") is not None
    getattr(RateLimiter, "for")("extra", lambda _r: Limit.per_minute(1))
    assert RateLimiter.limiter("extra") is not None


# --- throttle middleware ----------------------------------------------------


def test_numeric_throttle_returns_429_with_headers(client: TestClient) -> None:
    assert client.get("/burst").status_code == 200
    second = client.get("/burst")
    assert second.status_code == 200
    assert second.headers.get("x-ratelimit-limit") == "2"
    assert second.headers.get("x-ratelimit-remaining") == "0"
    denied = client.get("/burst")
    assert denied.status_code == 429
    assert denied.headers.get("retry-after") is not None
    assert denied.headers.get("x-ratelimit-remaining") == "0"


def test_named_limiter_on_route(client: TestClient) -> None:
    assert client.get("/uploads").status_code == 200
    assert client.get("/uploads").status_code == 200
    assert client.get("/uploads").status_code == 429


def test_limit_none_never_blocks(client: TestClient) -> None:
    for _ in range(5):
        assert client.get("/vip").status_code == 200


def test_custom_response_callback(client: TestClient) -> None:
    assert client.get("/custom").status_code == 200
    denied = client.get("/custom")
    assert denied.status_code == 429
    assert denied.json() == {"blocked": True}


def test_after_only_counts_matching_responses(client: TestClient) -> None:
    # 200s do not consume the budget.
    assert client.get("/found-thing").status_code == 200
    assert client.get("/found-thing").status_code == 200
    # First 404 consumes the only slot; second 404 is refused.
    assert client.get("/missing-thing").status_code == 404
    denied = client.get("/missing-thing")
    assert denied.status_code == 429


def test_throttle_api_is_on_the_api_group(client: TestClient) -> None:
    response = client.get("/api/ping")
    assert response.status_code == 200
    assert response.headers.get("x-ratelimit-limit") == "60"


def test_guest_auth_rate_string(client: TestClient) -> None:
    # Guests get the left half (2/min).
    assert client.get("/guest-auth").status_code == 200
    assert client.get("/guest-auth").status_code == 200
    assert client.get("/guest-auth").status_code == 429


# --- login throttling -------------------------------------------------------


def test_login_rate_limiter_locks_out(app_dir: Path) -> None:
    Application(app_dir).bootstrap()
    request = _fake_request()
    limiter = LoginRateLimiter(max_attempts=2, decay_seconds=60)
    RateLimiter.clear(limiter.key(request))
    assert limiter.too_many_attempts(request) is False
    limiter.hit(request)
    limiter.hit(request)
    assert limiter.too_many_attempts(request) is True
    with pytest.raises(TooManyRequestsHttpException) as raised:
        limiter.raise_for(request)
    assert "Retry-After" in raised.value.headers
    limiter.clear(request)
    assert limiter.too_many_attempts(request) is False


@pytest.mark.asyncio
async def test_attempt_login_hits_and_clears(
    app_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    Application(app_dir).bootstrap()
    request = _fake_request(email="u@example.com")

    class _Guard:
        def __init__(self) -> None:
            self.calls = 0

        async def attempt(self, credentials, remember=False):
            self.calls += 1
            return credentials.get("password") == "secret"

    guard = _Guard()

    class _Auth:
        def guard(self, name=None):
            return guard

    monkeypatch.setattr("almasix.auth.auth", lambda: _Auth())
    limiter = LoginRateLimiter(max_attempts=2, decay_seconds=60)
    RateLimiter.clear(limiter.key(request, "u@example.com"))

    assert (
        await attempt_login(
            {"email": "u@example.com", "password": "wrong"},
            request=request,
            limiter=limiter,
        )
        is False
    )
    assert (
        await attempt_login(
            {"email": "u@example.com", "password": "wrong"},
            request=request,
            limiter=limiter,
        )
        is False
    )
    with pytest.raises(TooManyRequestsHttpException):
        await attempt_login(
            {"email": "u@example.com", "password": "wrong"},
            request=request,
            limiter=limiter,
        )

    RateLimiter.clear(limiter.key(request, "u@example.com"))
    assert (
        await attempt_login(
            {"email": "u@example.com", "password": "secret"},
            request=request,
            limiter=limiter,
        )
        is True
    )
    assert RateLimiter.attempts(limiter.key(request, "u@example.com")) == 0


def test_throttle_middleware_instantiates_from_alias(app_dir: Path) -> None:
    app = Application(app_dir).bootstrap()
    mw = app.make(ThrottleRequests)
    assert isinstance(mw, ThrottleRequests)


def test_available_in_zero_when_clear(app_dir: Path) -> None:
    Application(app_dir).bootstrap()
    RateLimiter.clear("never-hit")
    assert RateLimiter.available_in("never-hit") == 0


def test_attempt_returns_true_when_callback_is_none(app_dir: Path) -> None:
    Application(app_dir).bootstrap()
    key = "silent"
    RateLimiter.clear(key)
    assert RateLimiter.attempt(key, 1, lambda: None) is True


def test_too_many_and_retries_tolerate_none_max(app_dir: Path) -> None:
    Application(app_dir).bootstrap()
    assert RateLimiter.too_many_attempts("x", None) is False  # type: ignore[arg-type]
    assert RateLimiter.retries_left("x", None) == 0  # type: ignore[arg-type]


def test_parse_rate_pipe_takes_the_left_half() -> None:
    assert parse_rate("10|60") == (10, 60)


def test_increment_recovers_when_store_increment_fails(
    app_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    Application(app_dir).bootstrap()
    monkeypatch.setattr(
        "almasix.cache.Cache.increment",
        lambda *_a, **_k: False,
    )
    RateLimiter.clear("broken")
    assert RateLimiter.increment("broken", decay_seconds=10, amount=2) == 2


def test_dedicated_limiter_store(app_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    Application(app_dir).bootstrap()
    from almasix.config import config as config_fn

    monkeypatch.setattr(
        "almasix.config.config",
        lambda key, default=None: "array" if key == "cache.limiter" else config_fn(key, default),
    )
    RateLimiter.clear("dedicated")
    assert RateLimiter.hit("dedicated") == 1


def test_store_falls_back_when_config_raises(
    app_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    Application(app_dir).bootstrap()

    def _boom(*_a, **_k):
        raise RuntimeError("no config")

    monkeypatch.setattr("almasix.config.config", _boom)
    assert RateLimiter._store() is not None


def test_named_limiter_returning_none_or_list(app_dir: Path) -> None:
    Application(app_dir).bootstrap()
    RateLimiter.for_("skip", lambda _r: None)
    RateLimiter.for_(
        "multi",
        lambda _r: [
            Limit.per_minute(1).by("a"),
            Limit.per_minute(1).by("b"),
        ],
    )
    mw_skip = ThrottleRequests("skip")
    mw_multi = ThrottleRequests("multi")
    request = _fake_request()
    assert mw_skip._limits_for(request) == []
    assert len(mw_multi._limits_for(request)) == 2


def test_default_key_prefers_authenticated_user(app_dir: Path) -> None:
    Application(app_dir).bootstrap()
    request = _fake_request()
    request.user = type("U", (), {"id": 42})()  # type: ignore[attr-defined]
    mw = ThrottleRequests("60,1")
    assert mw._default_key(request) == "user:42"
    request.user = lambda: type("U", (), {"id": 7})()  # type: ignore[attr-defined]
    assert mw._default_key(request) == "user:7"


def test_response_callback_arity_variants(app_dir: Path) -> None:
    Application(app_dir).bootstrap()
    mw = ThrottleRequests("60,1")
    request = _fake_request()
    assert mw._invoke_response(lambda: "zero", request, {}) == "zero"
    assert mw._invoke_response(lambda req: f"one:{req is request}", request, {}) == "one:True"

    # Builtins have no usable signature — fall through to zero-arg path carefully.
    class _Weird:
        def __call__(self, *args):
            return "weird"

        @property
        def __signature__(self):
            raise TypeError("no sig")

    # inspect.signature on a plain object without __signature__ still works;
    # force the except path via a callable that rejects signature.
    assert mw._invoke_response(_Weird(), request, {}) == "weird"


def test_attach_headers_skips_headerless_response(app_dir: Path) -> None:
    Application(app_dir).bootstrap()
    mw = ThrottleRequests("60,1")
    mw._attach_headers(object(), Limit.per_minute(1), "k")


def test_ip_helpers() -> None:
    from almasix.http.throttle import _ip

    class _Req:
        def header(self, key: str, default=None):
            if key == "x-forwarded-for":
                return "203.0.113.9, 10.0.0.1"
            return default

        raw = None

    assert _ip(_Req()) == "203.0.113.9"  # type: ignore[arg-type]

    class _Client:
        host = "198.51.100.2"

    class _Raw:
        client = _Client()

    class _Req2:
        def header(self, key: str, default=None):
            return default

        raw = _Raw()

    assert _ip(_Req2()) == "198.51.100.2"  # type: ignore[arg-type]

    class _Req3:
        def header(self, key: str, default=None):
            return default

        raw = None

    assert _ip(_Req3()) == "127.0.0.1"  # type: ignore[arg-type]
