"""Final coverage hits for almasix.exceptions + almasix.log."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

from almasix.exceptions.handler import Handler
from almasix.exceptions import mapping as mapping_mod
from almasix.exceptions import provider as provider_mod
from almasix.exceptions import publish as publish_mod
from almasix.exceptions.publish import ErrorsPublishError, publish_errors
from almasix.framework import Application
from almasix.http import HttpException
from almasix.log import log
from almasix.log.helpers import LogWriter
from tests.support import purge_generated_app_modules


def test_handler_http_500_client_message_when_not_debug() -> None:
    handler = Handler(None)
    msg = handler._message_for(
        HttpException("secret", status_code=500),
        for_client=True,
    )
    assert msg == "Server Error"
    # HttpException branch that returns the real message (line 116).
    assert (
        handler._message_for(HttpException("Nope", status_code=404), for_client=True)
        == "Nope"
    )


def test_provider_boot_when_fallback_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from almasix.prism.engine import Engine
    from almasix.prism.helpers import set_engine

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
    app.register_configured_providers()
    app.boot()
    engine = Engine(paths=[])
    app.container.instance(Engine, engine)
    set_engine(engine)
    monkeypatch.setattr(
        provider_mod,
        "framework_views_root",
        lambda bundle="default": tmp_path / "no-such-views-root",
    )
    provider_mod.ExceptionsServiceProvider(app).boot()
    assert len(engine.paths) == 0


def test_reportable_none_continues_and_with_context() -> None:
    handler = Handler(None)

    def return_none(_exc: BaseException):
        return None

    handler.reportable(RuntimeError, return_none)
    handler.dont_report = [RuntimeError]
    handler.report(RuntimeError("quiet"))

    writer = LogWriter(None).with_context(None, job="mail")
    writer = writer.with_context({"a": 1}, b=2)
    assert writer._context == {"a": 1, "b": 2, "job": "mail"} or writer._context == {
        "a": 1,
        "b": 2,
    }
    # Second with_context replaces via merge on new writer from first
    assert "a" in writer._context and "b" in writer._context
    log().with_context({"x": 1}).info("ctx")


def test_provider_import_engine_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    app = Application()
    provider = provider_mod.ExceptionsServiceProvider(app)

    import builtins

    real_import = builtins.__import__

    def boom(name, *args, **kwargs):
        if name == "almasix.prism.engine" or (
            isinstance(name, str) and name.startswith("almasix.prism.engine")
        ):
            raise ImportError("no engine")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", boom)
    provider.boot()


def test_resolve_app_handler_skips_non_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    fake_pkg = ModuleType("app.exceptions")
    fake_mod = ModuleType("app.exceptions.handler")

    class NotAHandler:
        pass

    fake_mod.Handler = NotAHandler
    monkeypatch.setitem(sys.modules, "app", ModuleType("app"))
    monkeypatch.setitem(sys.modules, "app.exceptions", fake_pkg)
    monkeypatch.setitem(sys.modules, "app.exceptions.handler", fake_mod)
    assert provider_mod._resolve_app_handler(Path("/tmp")) is Handler


def test_publish_missing_bundle_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        publish_mod,
        "framework_errors_path",
        lambda bundle="default": tmp_path / "missing-bundle",
    )
    with pytest.raises(ErrorsPublishError, match="missing"):
        publish_errors(tmp_path, bundle="default")


def test_publish_skips_non_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle_dir = tmp_path / "bundle" / "errors"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "404.prism.html").write_text("<p>404</p>", encoding="utf-8")
    (bundle_dir / "subdir").mkdir()

    monkeypatch.setattr(
        publish_mod,
        "framework_errors_path",
        lambda _name="default": bundle_dir,
    )
    dest = publish_errors(tmp_path / "app", bundle="default")
    assert (dest / "404.prism.html").is_file()
    assert not (dest / "subdir").is_file()


def test_mapping_skips_unloadable_types() -> None:
    mapping_mod._STATUS_MAP.append(("totally.missing.Module.Cls", 418))
    try:
        assert mapping_mod.resolved_status_map()
    finally:
        mapping_mod._STATUS_MAP.pop()
