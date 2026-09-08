"""Tests for Laravel-shaped ``dump()`` / ``dd()``."""

from __future__ import annotations

from pathlib import Path

import pytest

from almasix.console.command import Command
from almasix.console.kernel import ConsoleKernel
from almasix.debug import DumpAndDie, Caller, dd, dump, render_dd_html, render_dump_html, serialize
from almasix.exceptions.handler import Handler
from almasix.framework import Application
from tests.support import purge_generated_app_modules


def test_dump_returns_values_and_continues(capsys: pytest.CaptureFixture[str]) -> None:
    result = dump({"a": 1}, [2, 3])
    assert result == ({"a": 1}, [2, 3])
    captured = capsys.readouterr()
    text = captured.err + captured.out
    assert "a" in text or "dict" in text or "dump" in text.lower()


def test_dd_raises_dump_and_die() -> None:
    with pytest.raises(DumpAndDie) as caught:
        dd({"hello": "almasix"})
    assert caught.value.values == ({"hello": "almasix"},)
    assert caught.value.caller is not None
    assert isinstance(caught.value.caller, Caller)


def test_render_dd_html_contains_payload() -> None:
    caller = Caller(file="/app/controllers/demo.py", line=12, function="dump_demo")
    html = render_dd_html(
        ({"x": 1},),
        caller=caller,
        request_method="GET",
        request_path="/dd",
        app_name="Progress",
    )
    assert "Dump and die" in html
    assert "dd" in html
    assert 'class="k"' in html
    assert 'class="n"' in html
    assert "demo.py:12" in html or "controllers/demo.py:12" in html
    assert "Progress" in html


def test_handler_does_not_report_dd() -> None:
    handler = Handler()
    with pytest.raises(DumpAndDie) as caught:
        dd(1)
    assert handler.should_report(caught.value) is False


def test_handler_renders_web_html(tmp_path: Path) -> None:
    purge_generated_app_modules()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        'config = {"name": "DDApp", "debug": True, "providers": []}\n',
        encoding="utf-8",
    )
    app = Application(tmp_path)
    app.load_configuration()
    handler = Handler(app)

    class FakeRequest:
        method = "GET"
        path = "/dd"
        route_polarity = "web"
        route_name = None

    with pytest.raises(DumpAndDie) as caught:
        dd({"ok": True})
    response = handler.render(FakeRequest(), caught.value)  # type: ignore[arg-type]
    assert response.status_code == 200
    body = bytes(response.body).decode()
    assert "Dump and die" in body
    assert "DDApp" in body


def test_handler_renders_api_json(tmp_path: Path) -> None:
    handler = Handler()

    class FakeRequest:
        method = "GET"
        path = "/api/dd"
        route_polarity = "api"
        route_name = None

    with pytest.raises(DumpAndDie) as caught:
        dd({"api": True}, "second")
    response = handler.render(FakeRequest(), caught.value)  # type: ignore[arg-type]
    assert response.status_code == 200
    payload = response.body
    import json

    data = json.loads(payload)
    assert data["dd"] is True
    assert data["values"] == [{"api": True}, "second"]


class DdCommand(Command):
    signature = "demo:dd"
    description = "dd demo"

    def handle(self) -> int:
        dd({"from": "command"})
        return 1  # pragma: no cover


def test_console_kernel_dd_exits_zero(tmp_path: Path) -> None:
    purge_generated_app_modules()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        'config = {"name": "Console", "debug": False, "providers": []}\n',
        encoding="utf-8",
    )
    app = Application(tmp_path)
    app.load_configuration()
    kernel = ConsoleKernel(app)
    kernel.register(DdCommand)
    assert kernel.run_command("demo:dd") == 0


def test_render_dump_html_inline() -> None:
    html = render_dump_html({"name": "Ada"}, source="welcome")
    assert "almasix-dump" in html
    assert "welcome" in html
    assert 'class="k"' in html


def test_serialize_nested() -> None:
    assert serialize({"a": [1, {"b": 2}]}) == {"a": [1, {"b": 2}]}
