"""Controller action navigation and completions for the LSP."""

from __future__ import annotations

from pathlib import Path

import pytest

from almasix.lsp.analysis import call_at, context_at, find_controller_actions
from almasix.lsp.features import completions, definition, document_links, hover
from almasix.lsp.index import (
    AppIndex,
    build_index,
    controller_methods,
    discover_controllers,
    resolve_controller_action,
)
from tests.support import purge_generated_app_modules, without_base_path

PROGRESS = Path(__file__).resolve().parents[1] / "examples" / "progress"


@pytest.fixture()
def progress_index(monkeypatch: pytest.MonkeyPatch):
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    index = build_index(PROGRESS)
    assert index.ok, index.error
    return index


def test_discover_controllers_and_methods(progress_index) -> None:
    assert "ProgressController" in progress_index.controllers
    path = progress_index.controllers["ProgressController"]
    methods = controller_methods(path)
    assert "index" in methods
    assert "data" in methods
    assert "__init__" not in methods


def test_find_controller_actions_in_routes() -> None:
    src = 'Route.get("/progress", [ProgressController, "index"])\n'
    actions = find_controller_actions(src)
    assert len(actions) == 1
    assert actions[0].controller == "ProgressController"
    assert actions[0].value == "index"
    call = call_at(src, 0, src.find("index") + 1, language="python")
    assert call is not None and call.kind == "action"


def test_definition_jumps_to_controller_method(progress_index) -> None:
    src = 'Route.get("/progress", [ProgressController, "index"])\n'
    loc = definition(
        progress_index,
        src,
        0,
        src.find("index") + 1,
        language="python",
    )
    assert loc is not None
    assert loc.path == progress_index.controllers["ProgressController"]
    assert loc.start_line == controller_methods(loc.path)["index"]


def test_action_completions(progress_index) -> None:
    # Cursor inside an open action string.
    line = 'Route.get("/x", [ProgressController, "in'
    items = completions(progress_index, line, 0, len(line), language="python")
    labels = {item.label for item in items}
    assert "index" in labels
    assert all(item.kind == "action" for item in items)


def test_action_hover_and_links(progress_index) -> None:
    src = 'Route.get("/progress", [ProgressController, "index"])\n'
    pos = src.find("index") + 1
    tip = hover(progress_index, src, 0, pos, language="python")
    assert tip is not None and "ProgressController@index" in tip.contents
    links = document_links(progress_index, src, language="python")
    assert any("ProgressController" in (link.tooltip or "") for link in links)


def test_resolve_via_import(tmp_path: Path) -> None:
    ctrl = tmp_path / "app" / "http" / "controllers"
    ctrl.mkdir(parents=True)
    module = ctrl / "welcome_controller.py"
    module.write_text(
        "class WelcomeController:\n    async def index(self):\n        return None\n",
        encoding="utf-8",
    )
    index = AppIndex(
        base_path=tmp_path,
        controllers=discover_controllers(ctrl),
    )
    source = (
        "from app.http.controllers.welcome_controller import WelcomeController\n"
        'Route.get("/", [WelcomeController, "index"])\n'
    )
    resolved = resolve_controller_action(index, "WelcomeController", "index", source=source)
    assert resolved is not None
    assert resolved[0] == module.resolve()
    assert resolved[1] == 1


def test_context_at_open_action() -> None:
    line = '[FooController, "ba'
    ctx = context_at(line, 0, len(line), language="python")
    assert ctx is not None
    assert ctx.kind == "action"
    assert ctx.controller == "FooController"
    assert ctx.prefix == "ba"
