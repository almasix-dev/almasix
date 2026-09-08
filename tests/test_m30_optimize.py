"""M30 — the cache and warm-up family: ``cache:*``, ``view:*``, ``optimize``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from almasix.cache import Cache
from almasix.console.commands.optimize import (
    NOT_CACHED,
    CacheClearCommand,
    CacheForgetCommand,
    OptimizeClearCommand,
    OptimizeCommand,
    ViewCacheCommand,
    ViewClearCommand,
)
from almasix.console.kernel import ConsoleKernel
from almasix.prism.engine import Engine


def views_of(app: Any) -> Path:
    return Path(app.path("resources", "views"))


@pytest.fixture
def app(tmp_path: Path) -> Any:
    """A booted application with one template and an array cache."""
    views = tmp_path / "resources" / "views"
    views.mkdir(parents=True)
    (views / "welcome.prism.html").write_text("<p>{{ 'hello' }}</p>")

    from almasix.cache.provider import CacheServiceProvider
    from almasix.framework.application import Application
    from almasix.prism.provider import PrismServiceProvider

    application = Application(tmp_path)
    application.config.set("cache.default", "array")
    application.register(CacheServiceProvider)
    application.register(PrismServiceProvider)
    application.boot()
    return application


def run(command_cls: type, app: Any, capsys: pytest.CaptureFixture[str], **input: Any) -> tuple[int, str]:
    command = command_cls(app)
    kernel = ConsoleKernel(app)
    kernel.discover_framework_commands()
    command.kernel = kernel
    code = command.run(input.pop("arguments", None), input or None)
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def test_cache_clear_flushes_the_store(app: Any, capsys: pytest.CaptureFixture[str]) -> None:
    Cache.put("kept", "value")
    assert Cache.get("kept") == "value"

    code, text = run(CacheClearCommand, app, capsys)

    assert code == 0
    assert Cache.get("kept") is None
    assert "cleared" in text


def test_cache_clear_reports_a_store_that_will_not_flush(app: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(type(Cache.store()), "flush", lambda self: False)

    code, text = run(CacheClearCommand, app, capsys)

    assert code == 1
    assert "could not be flushed" in text


def test_cache_forget_removes_one_key_and_leaves_the_rest(app: Any, capsys: pytest.CaptureFixture[str]) -> None:
    Cache.put("gone", 1)
    Cache.put("stays", 2)

    code, text = run(CacheForgetCommand, app, capsys, arguments={"key": "gone"})

    assert code == 0
    assert Cache.get("gone") is None
    assert Cache.get("stays") == 2
    assert "gone forgotten" in text


def test_cache_forget_says_so_when_the_key_was_never_there(app: Any, capsys: pytest.CaptureFixture[str]) -> None:
    code, text = run(CacheForgetCommand, app, capsys, arguments={"key": "absent"})

    assert code == 0
    assert "was not in the cache" in text


def test_view_cache_compiles_every_template(app: Any, capsys: pytest.CaptureFixture[str]) -> None:
    code, text = run(ViewCacheCommand, app, capsys)

    assert code == 0
    # The application's one template, plus the pagination views the framework
    # ships — which this proves compile.
    assert "3 template(s) compiled" in text


def test_view_cache_reports_a_template_that_will_not_compile(app: Any, capsys: pytest.CaptureFixture[str]) -> None:
    broken = views_of(app) / "broken.prism.html"
    broken.write_text("@if\n  never\n@endif")

    code, text = run(ViewCacheCommand, app, capsys)

    assert code == 1
    assert "Nothing was cached" in text


def test_view_clear_drops_the_compiled_templates(app: Any, capsys: pytest.CaptureFixture[str]) -> None:
    engine = app.make(Engine)
    engine.cache_views()
    assert engine._cache

    code, text = run(ViewClearCommand, app, capsys)

    assert code == 0
    assert not engine._cache
    assert "Compiled views cleared" in text


def test_the_view_commands_report_an_application_without_an_engine(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from almasix.framework.application import Application

    bare = Application(tmp_path)  # never booted, so nothing is bound

    for command_cls in (ViewCacheCommand, ViewClearCommand):
        code, text = run(command_cls, bare, capsys)
        assert code == 1
        assert "No view engine is configured" in text


def test_optimize_caches_views_and_names_what_it_does_not_cache(app: Any, capsys: pytest.CaptureFixture[str]) -> None:
    code, text = run(OptimizeCommand, app, capsys)

    assert code == 0
    assert "template(s) compiled" in text
    for target in NOT_CACHED:
        assert target in text


def test_optimize_clear_clears_both_the_cache_and_the_views(app: Any, capsys: pytest.CaptureFixture[str]) -> None:
    Cache.put("kept", "value")
    engine = app.make(Engine)
    engine.cache_views()

    code, text = run(OptimizeClearCommand, app, capsys)

    assert code == 0
    assert Cache.get("kept") is None
    assert not engine._cache
    assert "cleared" in text


def test_optimize_clear_fails_when_a_step_fails(app: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(type(Cache.store()), "flush", lambda self: False)

    code, _ = run(OptimizeClearCommand, app, capsys)

    assert code == 1
