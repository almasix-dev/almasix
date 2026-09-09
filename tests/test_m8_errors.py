"""M8 — exception Handler, polarity rendering, logging, errors:publish."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from almasix.exceptions import publish_errors
from almasix.exceptions.publish import ErrorsPublishError
from almasix.framework import Application
from almasix.http import Controller, Middleware, NotFoundHttpException, Request, Response, html
from almasix.routing import Route, set_router
from tests.support import purge_generated_app_modules


class PageController(Controller):
    async def ok(self) -> Response:
        return html("<h1>ok</h1>")

    async def boom(self) -> Response:
        raise RuntimeError("web-boom")

    async def missing(self) -> Response:
        raise NotFoundHttpException("Missing page")


class ApiController(Controller):
    async def boom(self) -> dict[str, str]:
        raise RuntimeError("api-boom")

    async def missing(self) -> dict[str, str]:
        raise NotFoundHttpException("Missing api")


class StampMiddleware(Middleware):
    async def handle(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Stamp"] = "yes"
        return response


def _write_app(tmp_path: Path, *, debug: bool) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        f'config = {{"name": "M8", "debug": {debug!s}, "providers": []}}\n',
        encoding="utf-8",
    )
    (tmp_path / "config" / "http.py").write_text(
        "from tests.test_m8_errors import StampMiddleware\n"
        "config = {\n"
        "    'middleware': [],\n"
        "    'middleware_groups': {'web': [], 'api': ['stamp']},\n"
        "    'middleware_aliases': {'stamp': StampMiddleware},\n"
        "}\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "logging.py").write_text(
        "config = {\n"
        "    'default': 'null',\n"
        "    'channels': {'null': {'driver': 'null'}, 'stderr': {'driver': 'stderr'}},\n"
        "}\n",
        encoding="utf-8",
    )
    (tmp_path / "routes").mkdir()
    (tmp_path / "resources" / "views").mkdir(parents=True)
    (tmp_path / "storage" / "logs").mkdir(parents=True)


def _boot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, debug: bool) -> Application:
    purge_generated_app_modules()
    _write_app(tmp_path, debug=debug)
    monkeypatch.chdir(tmp_path)
    app = Application(tmp_path)
    app.load_environment()
    app.load_configuration()
    app.register_configured_providers()
    app.boot()
    set_router(app.router)
    with Route.group(middleware=["web"]):
        Route.get("/", [PageController, "ok"])
        Route.get("/boom", [PageController, "boom"])
        Route.get("/missing", [PageController, "missing"])
    with Route.group(prefix="/api", middleware=["api"]):
        Route.get("/boom", [ApiController, "boom"])
        Route.get("/missing", [ApiController, "missing"])
    app._routes_loaded = True
    return app


def test_api_json_envelope_and_middleware_stamp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _boot(tmp_path, monkeypatch, debug=False)
    client = TestClient(app.asgi, raise_server_exceptions=False)

    missing = client.get("/api/missing")
    assert missing.status_code == 404
    assert missing.json() == {"message": "Missing api", "status": 404, "errors": {}}
    assert missing.headers.get("x-stamp") == "yes"

    boom = client.get("/api/boom")
    assert boom.status_code == 500
    assert boom.json() == {"message": "Server Error", "status": 500, "errors": {}}
    assert boom.headers.get("x-stamp") == "yes"


def test_api_debug_widens_message_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _boot(tmp_path, monkeypatch, debug=True)
    client = TestClient(app.asgi, raise_server_exceptions=False)
    boom = client.get("/api/boom")
    assert boom.status_code == 500
    body = boom.json()
    assert body["status"] == 500
    assert body["message"] == "api-boom"
    assert "traceback" not in body
    assert "Traceback" not in str(body)


def test_web_production_error_view(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _boot(tmp_path, monkeypatch, debug=False)
    client = TestClient(app.asgi, raise_server_exceptions=False)
    missing = client.get("/missing")
    assert missing.status_code == 404
    assert "text/html" in missing.headers["content-type"]
    assert "404" in missing.text
    assert "Missing page" in missing.text


def test_web_debug_page_gated_on_app_debug(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _boot(tmp_path, monkeypatch, debug=True)
    client = TestClient(app.asgi, raise_server_exceptions=False)
    boom = client.get("/boom")
    assert boom.status_code == 500
    assert "text/html" in boom.headers["content-type"]
    assert "RuntimeError" in boom.text
    assert "web-boom" in boom.text
    assert "Almasix debug page" in boom.text

    # APP_ENV alone must not keep the debug page when APP_DEBUG is false.
    app.config.set("app.env", "local")
    app.config.set("app.debug", False)
    app._asgi = None
    client = TestClient(app.asgi, raise_server_exceptions=False)
    prod = client.get("/boom")
    assert prod.status_code == 500
    assert "Almasix debug page" not in prod.text
    assert "500" in prod.text


def test_accept_json_on_web_still_html(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _boot(tmp_path, monkeypatch, debug=False)
    client = TestClient(app.asgi, raise_server_exceptions=False)
    response = client.get("/missing", headers={"Accept": "application/json"})
    assert response.status_code == 404
    assert "text/html" in response.headers["content-type"]


def test_errors_publish_bundles(tmp_path: Path) -> None:
    dest = publish_errors(tmp_path, bundle="default")
    assert (dest / "404.prism.html").is_file()
    assert "--brand:#f1511b" in (dest / "404.prism.html").read_text(encoding="utf-8")
    publish_errors(tmp_path, bundle="tailwind", force=True)
    body = (dest / "404.prism.html").read_text(encoding="utf-8")
    assert "--brand:#f1511b" in body
    assert "Back to {{ name }}" in body
    assert "cdn.tailwindcss.com" not in body
    publish_errors(tmp_path, bundle="bootstrap", force=True)
    body = (dest / "404.prism.html").read_text(encoding="utf-8")
    assert "--brand:#f1511b" in body
    assert "cdn.jsdelivr.net" not in body
    with pytest.raises(ErrorsPublishError):
        publish_errors(tmp_path, bundle="nope")


def test_status_mapping_model_not_found() -> None:
    from almasix.exceptions.mapping import status_for_exception
    from almasix.http import ServiceUnavailableHttpException
    from almasix.orm import ModelNotFoundError

    assert status_for_exception(ModelNotFoundError("Post")) == 404
    assert status_for_exception(ServiceUnavailableHttpException()) == 503


def test_model_not_found_renders_404(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from almasix.orm import ModelNotFoundError

    app = _boot(tmp_path, monkeypatch, debug=False)

    class Missing(Controller):
        async def show(self) -> dict:
            raise ModelNotFoundError("Post")

    with Route.group(prefix="/api", middleware=["api"]):
        Route.get("/posts/missing", [Missing, "show"])
    with Route.group(middleware=["web"]):
        Route.get("/posts/missing", [Missing, "show"])

    client = TestClient(app.asgi, raise_server_exceptions=False)
    api = client.get("/api/posts/missing")
    assert api.status_code == 404
    assert api.json()["status"] == 404

    page = client.get("/posts/missing")
    assert page.status_code == 404
    assert "text/html" in page.headers["content-type"]


def test_unmatched_routes_use_path_polarity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _boot(tmp_path, monkeypatch, debug=False)
    client = TestClient(app.asgi, raise_server_exceptions=False)
    web = client.get("/definitely-missing")
    assert web.status_code == 404
    assert "text/html" in web.headers["content-type"]
    api = client.get("/api/definitely-missing")
    assert api.status_code == 404
    assert api.json()["status"] == 404


def test_fallback_html_without_engine() -> None:
    from almasix.exceptions.handler import Handler
    from almasix.prism.helpers import set_engine

    set_engine(None)
    handler = Handler(None)
    req = Request(
        SimpleNamespace(
            method="GET",
            url=SimpleNamespace(path="/x"),
            headers={},
            cookies={},
        )
    )
    req.route_polarity = "web"
    response = handler.render(req, RuntimeError("x"))
    assert response.status_code == 500
    assert b"<h1>500</h1>" in response.body


def test_mapping_and_publish_edges(tmp_path: Path) -> None:
    from almasix.exceptions.mapping import (
        _load_type,
        default_message_for_status,
        polarity_from_path,
        register_status,
        resolved_status_map,
        status_for_exception,
    )
    from almasix.exceptions.publish import ErrorsPublishError, framework_views_root, publish_errors

    assert polarity_from_path("/api") == "api"
    assert polarity_from_path("/api/") == "api"
    assert polarity_from_path("/about") == "web"
    assert _load_type("nope") is None
    assert _load_type("almasix.exceptions.mapping.not_a_type") is None
    assert resolved_status_map()

    class CustomBoom(Exception):
        pass

    register_status(CustomBoom, 418)
    assert status_for_exception(CustomBoom()) == 418
    assert "Not Found" in default_message_for_status(404)
    assert "Server Error" in default_message_for_status(599)

    # force=False skips existing
    publish_errors(tmp_path, bundle="default")
    first = (tmp_path / "resources" / "views" / "errors" / "404.prism.html").read_text(
        encoding="utf-8"
    )
    (tmp_path / "resources" / "views" / "errors" / "404.prism.html").write_text(
        "KEEP", encoding="utf-8"
    )
    publish_errors(tmp_path, bundle="default", force=False)
    assert (tmp_path / "resources" / "views" / "errors" / "404.prism.html").read_text(
        encoding="utf-8"
    ) == "KEEP"
    assert framework_views_root("default").is_dir()
    with pytest.raises(ErrorsPublishError):
        framework_views_root("nope")
    del first


def test_handler_try_view_and_http_warning_branches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from almasix.exceptions.handler import Handler
    from almasix.http import HttpException

    app = _boot(tmp_path, monkeypatch, debug=True)
    handler = app.make(Handler)
    # Force report path for HttpException <500 after clearing should_report bypass
    # by calling logger warning branch directly after should_report True override.
    original = handler.should_report
    handler.should_report = lambda exc: True  # type: ignore[method-assign]
    handler.report(HttpException("soft", status_code=404))
    handler.should_report = original  # type: ignore[method-assign]

    assert handler._try_view("errors.nope", 404, "x") is None
    monkeypatch.setattr(
        "almasix.prism.helpers.get_engine",
        lambda: (_ for _ in ()).throw(RuntimeError("down")),
    )
    assert handler._try_view("errors.404", 404, "x") is None

    # Import failure in _try_view
    import builtins

    real_import = builtins.__import__

    def boom_import(name, *args, **kwargs):
        if name.startswith("almasix.prism"):
            raise ImportError("no prism")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", boom_import)
    assert handler._try_view("errors.404", 404, "x") is None


def test_provider_boot_without_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from almasix.exceptions.provider import ExceptionsServiceProvider
    from almasix.framework import Application

    purge_generated_app_modules()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        'config = {"name": "P", "debug": False, "providers": []}\n',
        encoding="utf-8",
    )
    (tmp_path / "routes").mkdir()
    monkeypatch.chdir(tmp_path)
    app = Application(tmp_path)
    app.load_environment()
    app.load_configuration()
    # Provider boot when Engine unbound is a no-op.
    ExceptionsServiceProvider(app).boot()


def test_remaining_m8_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from almasix.exceptions import mapping as mapping_mod
    from almasix.exceptions.handler import Handler
    from almasix.exceptions.publish import publish_errors
    from almasix.log.helpers import LogWriter
    from almasix.log.manager import LogManager, set_log_manager

    app = _boot(tmp_path, monkeypatch, debug=False)
    handler = app.make(Handler)

    def keep_going(_exc: BaseException) -> bool:
        return True

    handler.reportable(RuntimeError, keep_going)
    handler.report(RuntimeError("kept"))

    class ReportTrue(Exception):
        def report(self):
            return True

    handler.report(ReportTrue())

    def none_render(_req, _exc):
        return None

    handler.renderable(ValueError, none_render)
    req = Request(
        SimpleNamespace(method="GET", url=SimpleNamespace(path="/"), headers={}, cookies={})
    )
    req.route_polarity = "api"
    assert handler.render(req, ValueError("v")).status_code == 500

    # _message_for non-client / empty str
    assert handler._message_for(RuntimeError(""), for_client=False) == "RuntimeError"
    bare = Handler(None)
    assert bare._debug() is False
    assert bare._message_for(RuntimeError("x"), for_client=True) == "Server Error"

    # mapping import failure + translation fallback
    monkeypatch.setattr(
        mapping_mod,
        "__import__",
        lambda *a, **k: (_ for _ in ()).throw(ImportError("x")),
        raising=False,
    )
    # force except path via _load_type with bad module that raises
    assert mapping_mod._load_type("builtins.NonexistentTypeXYZ") is None

    def boom_trans(key):
        raise RuntimeError("no translator")

    monkeypatch.setattr(
        "almasix.exceptions.mapping.__",
        boom_trans,
        raising=False,
    )
    # Call through default_message which tries __ then falls back
    from almasix.exceptions.mapping import default_message_for_status

    # Directly exercise fallbacks by patching the import inside the function
    monkeypatch.setattr(
        "almasix.translation.__",
        lambda key: (_ for _ in ()).throw(RuntimeError("down")),
    )
    assert default_message_for_status(404) == "Not Found"

    # publish with empty source files skipped (directories only already covered)
    publish_errors(tmp_path, bundle="default", force=True)

    # log error/critical + empty stack with child that has no handlers yet
    set_log_manager(LogManager(app))
    LogWriter("stderr").error("e")
    LogWriter("stderr").critical("c")
    app.config.set(
        "logging.channels",
        {
            "childless": {"driver": "stack", "channels": ["missing-child"]},
            "missing-child": {"driver": "null"},
        },
    )
    LogManager(app)  # build the stack channel so the next config swap has a baseline
    # null has NullHandler — stack should copy it; for empty handlers path use
    # a child that clears handlers
    app.config.set(
        "logging.channels",
        {"lonely": {"driver": "stack", "channels": ["ghost"]}, "ghost": {"driver": "stderr"}},
    )
    lonely = LogManager(app)
    lonely._loggers["ghost"] = __import__("logging").getLogger("almasix.channel.ghost")
    lonely._loggers["ghost"].handlers.clear()
    lonely.channel("lonely").info("needs-fallback")
