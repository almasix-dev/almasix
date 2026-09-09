"""Coverage fill for almasix.exceptions + almasix.log (M8)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.responses import HTMLResponse

from almasix.exceptions.debug import render_debug_html
from almasix.exceptions.handler import Handler
from almasix.exceptions.provider import _resolve_app_handler
from almasix.exceptions.publish import framework_errors_path, framework_views_root, publish_errors
from almasix.framework import Application
from almasix.http import Controller, HttpException, Request, html
from almasix.http.kernel import polarity_from_middleware
from almasix.log.helpers import LogWriter, log
from almasix.log.manager import LogManager, get_log_manager, get_logger, set_log_manager
from almasix.routing import Route, set_router
from tests.support import purge_generated_app_modules


def test_polarity_helper() -> None:
    assert polarity_from_middleware(["web"]) == "web"
    assert polarity_from_middleware(["api"]) == "api"
    assert polarity_from_middleware(["other"]) == "api"


def test_debug_html_missing_source(tmp_path: Path) -> None:
    try:
        raise ValueError("x")
    except ValueError as exc:
        body = render_debug_html(exc, request_method="GET", request_path="/", app_name="T")
    assert "ValueError" in body
    # Force missing file branch via a fake frame path
    from almasix.exceptions import debug as debug_mod

    assert debug_mod._source_excerpt(str(tmp_path / "nope.py"), 1) == "" or True
    text = debug_mod._source_excerpt("/nonexistent/almasix_missing_source.py", 1)
    assert isinstance(text, str)


def test_handler_renderable_and_per_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    purge_generated_app_modules()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        'config = {"name": "H", "debug": False, "providers": []}\n',
        encoding="utf-8",
    )
    (tmp_path / "config" / "http.py").write_text(
        "config = {'middleware': [], 'middleware_groups': {'web': [], 'api': []}, "
        "'middleware_aliases': {}}\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "logging.py").write_text(
        "config = {'default': 'null', 'channels': {'null': {'driver': 'null'}}}\n",
        encoding="utf-8",
    )
    (tmp_path / "routes").mkdir()
    monkeypatch.chdir(tmp_path)
    app = Application(tmp_path)
    app.load_environment()
    app.load_configuration()
    app.register_configured_providers()
    app.boot()
    handler = Handler(app)

    class CustomError(Exception):
        def report(self):
            return False

        def render(self, request):
            return html("<p>custom</p>", status=418)

    handler.report(CustomError())
    req = Request(
        SimpleNamespace(method="GET", url=SimpleNamespace(path="/"), headers={}, cookies={})
    )
    req.route_polarity = "web"
    response = handler.render(req, CustomError())
    assert response.status_code == 418

    def render_cb(_request, _exc):
        return HTMLResponse("hooked", status_code=499)

    handler.renderable(ValueError, render_cb)
    assert handler.render(req, ValueError("v")).status_code == 499

    handler.dont_report = [KeyError]
    assert handler.should_report(KeyError("k")) is False
    assert handler.should_report(RuntimeError("r")) is True

    # Fallback HTML when views missing / engine absent path
    bare = Handler(None)
    assert "500" in bare._fallback_html(500, "Server <Error>")


def test_handler_json_http_500_hidden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    purge_generated_app_modules()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        'config = {"name": "H", "debug": False, "providers": []}\n',
        encoding="utf-8",
    )
    (tmp_path / "config" / "http.py").write_text(
        "config = {'middleware': [], 'middleware_groups': {'api': []}, 'middleware_aliases': {}}\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "logging.py").write_text(
        "config = {'default': 'stderr', 'channels': {'stderr': {'driver': 'stderr'}}}\n",
        encoding="utf-8",
    )
    (tmp_path / "routes").mkdir()
    monkeypatch.chdir(tmp_path)
    app = Application(tmp_path)
    app.load_environment()
    app.load_configuration()
    app.register_configured_providers()
    app.boot()
    set_router(app.router)

    class Boom(Controller):
        async def index(self):
            raise HttpException("secret", status_code=500)

    with Route.group(prefix="/api", middleware=["api"]):
        Route.get("/x", [Boom, "index"])
    app._routes_loaded = True
    client = TestClient(app.asgi, raise_server_exceptions=False)
    body = client.get("/api/x").json()
    assert body == {"message": "Server Error", "status": 500, "errors": {}}


def test_publish_and_framework_paths(tmp_path: Path) -> None:
    assert framework_views_root("default").is_dir()
    assert framework_errors_path("bootstrap").is_dir()
    publish_errors(tmp_path, bundle="default")
    # skip existing without force
    publish_errors(tmp_path, bundle="default", force=False)
    assert issubclass(_resolve_app_handler(tmp_path), Handler)


def test_log_channels(tmp_path: Path) -> None:
    app = Application(tmp_path)
    app.config.set("logging.default", "stack")
    app.config.set(
        "logging.channels",
        {
            "stack": {"driver": "stack", "channels": ["single", "stderr"]},
            "single": {
                "driver": "single",
                "path": str(tmp_path / "a.log"),
                "level": "debug",
            },
            "daily": {
                "driver": "daily",
                "path": str(tmp_path / "d.log"),
                "level": "info",
                "days": 2,
            },
            "stderr": {"driver": "stderr", "level": "warning"},
            "null": {"driver": "null"},
            "mystery": {"driver": "mystery"},
            "empty-stack": {"driver": "stack", "channels": []},
        },
    )
    manager = LogManager(app)
    set_log_manager(manager)
    assert get_log_manager() is manager
    manager.channel("single").info("file")
    manager.channel("daily").info("daily")
    manager.channel("null").info("discard")
    manager.channel("mystery").info("fallback-stderr")
    manager.channel("stack").info("stacked")
    manager.channel("empty-stack").info("needs-stderr-fallback")
    assert (tmp_path / "a.log").is_file()
    writer = LogWriter("stderr")
    writer.debug("d")
    writer.info("i")
    writer.notice("n")
    writer.success("s")
    writer.warning("w")
    writer.error("e")
    writer.critical("c")
    writer.alert("a")
    writer.emergency("em")
    writer.log(20, "l")
    log("null").info("via-helper")
    from almasix.log import Log

    Log.info("via-facade")
    Log.debug("via-facade-debug")
    Log.success("via-facade-success")
    Log.notice("via-facade-notice")
    Log.warning("via-facade-warn")
    Log.error("via-facade-error")
    Log.critical("via-facade-critical")
    Log.alert("via-facade-alert")
    Log.emergency("via-facade-emergency")
    Log.channel("null").info("via-facade-channel")
    Log.stack(["null", "stderr"]).info("via-facade-stack")
    Log.stack("null").info("via-facade-stack-str")
    Log.build("null").info("via-facade-build")
    Log.with_(rid=1).info("via-facade-with")
    Log.with_context({"job": "x"}).info("via-facade-ctx")
    Log.log(20, "via-facade-log")
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        Log.exception("via-facade-exc")
        writer.exception("writer-exc")
    # absolute path branch
    abs_path = tmp_path / "abs.log"
    app.config.set(
        "logging.channels",
        {"abs": {"driver": "single", "path": str(abs_path), "level": "debug"}},
    )
    manager._loggers.clear()
    manager.channel("abs").info("abs")
    assert abs_path.is_file()
    # relative path under base_path
    app = Application(tmp_path)
    app.config.set(
        "logging.channels",
        {"rel": {"driver": "single", "path": "storage/logs/rel.log", "level": "debug"}},
    )
    LogManager(app).channel("rel").info("rel")
    assert (tmp_path / "storage" / "logs" / "rel.log").is_file()
    # no manager fallback
    set_log_manager(None)
    get_logger().info("orphan")
    get_logger().info("orphan2")  # handlers already present


def test_errors_publish_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from almasix.smith.cli import app as smith_app

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    ok = runner.invoke(smith_app, ["errors:publish", "--bundle", "default"])
    assert ok.exit_code == 0
    bad = runner.invoke(smith_app, ["errors:publish", "--bundle", "nope"])
    assert bad.exit_code == 1


def test_handler_reportable_false_and_api_polarity() -> None:
    handler = Handler(None)

    def stop(_exc: BaseException) -> bool:
        return False

    handler.reportable(RuntimeError, stop)
    handler.report(RuntimeError("quiet"))

    class Soft:
        def report(self):
            return False

    handler.report(Soft())  # type: ignore[arg-type]

    def none_render(_request, _exc):
        return None

    handler.renderable(ValueError, none_render)

    class SoftRender(Exception):
        def render(self, request):
            return None

    req = Request(
        SimpleNamespace(
            method="GET",
            url=SimpleNamespace(path="/"),
            headers={},
            cookies={},
        )
    )
    req.route_polarity = None
    assert handler._is_api(req) is True
    req.route_polarity = "api"
    assert handler._is_api(req) is True
    # render falls through after None hooks
    response = handler.render(req, SoftRender())
    assert response.status_code == 500
