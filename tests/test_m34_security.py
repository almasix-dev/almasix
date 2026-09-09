"""M34 — security headers, CORS, and maintenance mode over HTTP."""

from __future__ import annotations

import json
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from almasix.framework import Application
from almasix.http.cors import _path_matches, cors_settings
from almasix.http.maintenance import (
    BYPASS_COOKIE,
    clear_marker,
    maintenance_payload,
    write_marker,
)
from almasix.http.security import DEFAULT_HEADERS, SecurityHeaders, csp_nonce
from tests.support import purge_generated_app_modules


def _write(root: Path, relative: str, body: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")


@pytest.fixture()
def app_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    purge_generated_app_modules()
    _write(tmp_path, ".env", "APP_NAME=SecureApp\nAPP_DEBUG=true\n")
    for package in ("app", "app/http", "app/http/controllers"):
        _write(tmp_path, f"{package}/__init__.py", "")
    _write(
        tmp_path,
        "config/app.py",
        'config = {"name": "SecureApp", "debug": True, "url": "http://testserver", "providers": []}\n',
    )
    _write(
        tmp_path,
        "config/http.py",
        "config = {'middleware': [], 'middleware_groups': {'web': [], 'api': []}, "
        "'middleware_aliases': {}}\n",
    )
    _write(
        tmp_path,
        "config/cors.py",
        "config = {\n"
        "    'paths': ['api/*'],\n"
        "    'allowed_methods': ['*'],\n"
        "    'allowed_origins': ['https://app.test'],\n"
        "    'allowed_headers': ['*'],\n"
        "    'supports_credentials': False,\n"
        "    'max_age': 600,\n"
        "}\n",
    )
    _write(
        tmp_path,
        "bootstrap/app.py",
        """
        from pathlib import Path
        from almasix.framework import Application, Middleware

        BASE_PATH = Path(__file__).resolve().parent.parent


        def configure(middleware: Middleware) -> None:
            pass


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
        from almasix.http.security import csp_nonce
        from almasix.routing import Route

        Route.get("/", lambda: {"ok": True}, name="home")
        with Route.group(middleware=["web"]):
            Route.get("/page", lambda: {"nonce": csp_nonce()}, name="page")
        with Route.group(prefix="/api", middleware=["api"]):
            Route.get("/ping", lambda: {"pong": True}, name="api.ping")
            Route.options("/ping", lambda: {"preflight": True})
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
    application = Application(app_dir).bootstrap()
    with TestClient(application.asgi) as test_client:
        yield test_client


# --- security headers -------------------------------------------------------


def test_a_web_route_carries_the_default_security_headers(client: TestClient) -> None:
    response = client.get("/page")

    assert response.status_code == 200
    for name, value in DEFAULT_HEADERS.items():
        assert response.headers.get(name.lower()) == value


def test_an_api_route_does_not_get_security_headers_by_default(client: TestClient) -> None:
    response = client.get("/api/ping")

    assert response.headers.get("x-content-type-options") is None


def test_the_csp_nonce_reaches_the_handler(client: TestClient) -> None:
    response = client.get("/page")

    assert response.json()["nonce"]
    assert len(response.json()["nonce"]) >= 16


async def test_security_headers_can_carry_csp_and_hsts() -> None:
    from almasix.http.request import Request

    class Fake:
        url = "https://shop.test/"
        headers = {"x-forwarded-proto": "https"}

        def header(self, key: str, default: object = None) -> object:
            return self.headers.get(key, default)

    middleware = SecurityHeaders(
        csp="default-src 'self'; script-src 'nonce-{nonce}'",
        hsts=True,
    )
    request = Request(Fake())  # type: ignore[arg-type]

    async def call_next(req: Request) -> object:
        class Response:
            headers: dict[str, str] = {}

        return Response()

    response = await middleware.handle(request, call_next)
    assert "nonce-" in response.headers["Content-Security-Policy"]
    assert response.headers["Strict-Transport-Security"].startswith("max-age=")
    assert csp_nonce(request)
    assert csp_nonce() == ""  # no current request outside the pipeline


# --- CORS -------------------------------------------------------------------


def test_a_matching_api_path_answers_cors_headers(client: TestClient) -> None:
    response = client.options(
        "/api/ping",
        headers={
            "Origin": "https://app.test",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.headers.get("access-control-allow-origin") == "https://app.test"
    assert response.headers.get("access-control-max-age") == "600"


def test_a_path_outside_cors_paths_stays_quiet(client: TestClient) -> None:
    response = client.get("/", headers={"Origin": "https://app.test"})

    assert response.headers.get("access-control-allow-origin") is None


@pytest.mark.parametrize(
    ("pattern", "path", "matches"),
    [
        ("api/*", "/api/ping", True),
        ("api/*", "/api", True),
        ("api/*", "/other", False),
        ("exact", "/exact", True),
        ("exact", "/exact/no", False),
        ("foo*", "/foobar", True),
    ],
)
def test_cors_path_patterns(pattern: str, path: str, matches: bool) -> None:
    assert _path_matches(pattern, path) is matches


def test_cors_settings_merge_onto_the_defaults() -> None:
    assert cors_settings({"allowed_origins": ["https://a.test"]})["paths"] == [
        "api/*",
        "sanctum/csrf-cookie",
    ]
    assert cors_settings()["allowed_origins"] == ["*"]


# --- maintenance mode -------------------------------------------------------


def test_smith_down_answers_503_and_up_clears_it(client: TestClient, app_dir: Path) -> None:
    write_marker(app_dir, retry=60)
    try:
        response = client.get("/")
        assert response.status_code == 503
        assert response.headers.get("retry-after") == "60"
    finally:
        clear_marker(app_dir)

    assert client.get("/").status_code == 200


def test_a_secret_grants_a_bypass_cookie(client: TestClient, app_dir: Path) -> None:
    write_marker(app_dir, secret="let-me-in")
    try:
        denied = client.get("/")
        assert denied.status_code == 503

        granted = client.get("/?secret=let-me-in", follow_redirects=False)
        assert granted.status_code == 302
        assert BYPASS_COOKIE in granted.headers.get("set-cookie", "")

        # The TestClient keeps cookies across requests.
        assert client.get("/").status_code == 200
        assert client.get("/page").json()["nonce"]
    finally:
        clear_marker(app_dir)


def test_a_redirect_payload_sends_the_visitor_elsewhere(client: TestClient, app_dir: Path) -> None:
    write_marker(app_dir, redirect="/elsewhere", retry=30)
    try:
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/elsewhere"
        assert response.headers["retry-after"] == "30"
    finally:
        clear_marker(app_dir)


def test_the_legacy_plaintext_marker_still_means_down(client: TestClient, app_dir: Path) -> None:
    # M31 wrote the word "down". An application taken down before this
    # middleware existed must still answer 503, not 500.
    marker = app_dir / "storage" / "framework" / "down"
    marker.write_text("down", encoding="utf-8")
    try:
        assert client.get("/").status_code == 503
    finally:
        marker.unlink()


def test_write_marker_records_every_option(app_dir: Path) -> None:
    path = write_marker(
        app_dir,
        secret="s",
        redirect="/r",
        retry=15,
        refresh=10,
        status=503,
        render="errors.503",
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["secret"] == "s"
    assert payload["redirect"] == "/r"
    assert payload["retry"] == 15
    assert payload["refresh"] == 10
    assert payload["render"] == "errors.503"
    clear_marker(app_dir)
    assert maintenance_payload() is None


def test_the_down_command_writes_a_json_marker(app_dir: Path) -> None:
    from almasix.console.commands.maintenance import DownCommand, UpCommand

    application = Application(app_dir).bootstrap()
    down = DownCommand()
    down.app = application
    down._options = {
        "secret": "x",
        "retry": "45",
        "with-secret": False,
        "redirect": None,
        "render": None,
        "refresh": None,
        "status": 503,
    }
    down._arguments = {}
    assert down.handle() == 0
    payload = json.loads((app_dir / "storage" / "framework" / "down").read_text(encoding="utf-8"))
    assert payload["secret"] == "x"
    assert payload["retry"] == 45

    up = UpCommand()
    up.app = application
    up._options = {}
    up._arguments = {}
    assert up.handle() == 0
    assert not (app_dir / "storage" / "framework" / "down").exists()


async def test_security_headers_accept_overrides_and_removals() -> None:
    from starlette.datastructures import URL, Headers

    from almasix.http.request import Request

    class Fake:
        url = URL("http://shop.test/")
        headers = Headers()

    middleware = SecurityHeaders(
        headers={"X-Frame-Options": "DENY"},
        remove=["X-XSS-Protection"],
        hsts="max-age=60",
    )
    request = Request(Fake())  # type: ignore[arg-type]

    async def call_next(req: Request) -> object:
        class Response:
            headers: dict[str, str] = {}

        return Response()

    response = await middleware.handle(request, call_next)
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "X-XSS-Protection" not in response.headers
    # HSTS stays off on plain HTTP even when configured.
    assert "Strict-Transport-Security" not in response.headers


def test_an_excepted_uri_passes_through_maintenance(app_dir: Path) -> None:
    import asyncio

    from starlette.datastructures import URL, Headers

    from almasix.http.maintenance import PreventRequestsDuringMaintenance
    from almasix.http.request import Request

    write_marker(app_dir)
    try:

        class Fake:
            url = URL("http://testserver/up")
            headers = Headers()

            def query(self, key: str | None = None, default: object = None) -> object:
                return default

            def cookie(self, key: str, default: object = None) -> object:
                return default

        middleware = PreventRequestsDuringMaintenance(except_=["/up"])
        request = Request(Fake())  # type: ignore[arg-type]

        async def call_next(req: Request) -> str:
            return "ok"

        assert asyncio.run(middleware.handle(request, call_next)) == "ok"
    finally:
        clear_marker(app_dir)


def test_an_empty_marker_and_a_refresh_header(client: TestClient, app_dir: Path) -> None:
    marker = app_dir / "storage" / "framework" / "down"
    marker.write_text("\n", encoding="utf-8")
    try:
        assert client.get("/").status_code == 503
    finally:
        marker.unlink()

    write_marker(app_dir, refresh=5, template="missing.view")
    try:
        response = client.get("/")
        # A missing view still answers 503; Refresh is set when asked for.
        assert response.status_code == 503
        assert response.headers.get("refresh") == "5"
    finally:
        clear_marker(app_dir)


def test_down_with_secret_flag_generates_one(app_dir: Path) -> None:
    from almasix.console.commands.maintenance import DownCommand
    from almasix.framework import Application

    application = Application(app_dir).bootstrap()
    command = DownCommand()
    command.app = application
    command._options = {
        "with-secret": True,
        "secret": None,
        "retry": None,
        "redirect": None,
        "render": None,
        "refresh": None,
        "status": 503,
    }
    command._arguments = {}
    assert command.handle() == 0
    payload = json.loads((app_dir / "storage" / "framework" / "down").read_text(encoding="utf-8"))
    assert payload["secret"]
    clear_marker(app_dir)


def test_a_non_mapping_json_marker_is_treated_as_empty(client: TestClient, app_dir: Path) -> None:
    marker = app_dir / "storage" / "framework" / "down"
    marker.write_text("[]", encoding="utf-8")
    try:
        assert client.get("/").status_code == 503
    finally:
        marker.unlink()
