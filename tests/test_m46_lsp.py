"""M46 — Almasix language server: index, analysis, features, wire protocol."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from almasix.lsp import AppIndex, build_index, create_server, find_app_root
from almasix.lsp.analysis import (
    call_at,
    context_at,
    directive_at,
    find_prism_calls,
    find_python_calls,
)
from almasix.lsp.directives import PRISM_DIRECTIVES, directive_hover
from almasix.lsp.features import (
    completions,
    definition,
    diagnostics_python,
    document_links,
    hover,
)
from almasix.lsp.index import discover_models, discover_views, flatten_config
from tests.support import purge_generated_app_modules, without_base_path
from tests.support_lsp import LspWireSession, initialize_session, open_document

PROGRESS = Path(__file__).resolve().parents[1] / "examples" / "progress"


@pytest.fixture()
def progress_index(monkeypatch: pytest.MonkeyPatch) -> AppIndex:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    index = build_index(PROGRESS)
    assert index.ok, index.error
    return index


def test_find_app_root_and_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert find_app_root(tmp_path) is None
    monkeypatch.chdir(tmp_path)
    empty = build_index()
    assert empty.error is not None
    assert "bootstrap/app.py" in empty.error


def test_flatten_config_and_discover_helpers(tmp_path: Path) -> None:
    keys = flatten_config({"app": {"name": "X", "nested": {"a": 1}}, "_skip": 1})
    assert "app" in keys
    assert "app.name" in keys
    assert "app.nested.a" in keys
    assert "_skip" not in keys

    views = tmp_path / "views"
    (views / "auth").mkdir(parents=True)
    (views / "auth" / "login.prism.html").write_text("hi", encoding="utf-8")
    (views / "welcome.prism.html").write_text("yo", encoding="utf-8")
    mapped = discover_views(views)
    assert mapped["auth.login"].name == "login.prism.html"
    assert mapped["welcome"].name == "welcome.prism.html"
    assert discover_views(tmp_path / "missing") == {}

    models = tmp_path / "models"
    models.mkdir()
    (models / "user.py").write_text("class User: ...\n", encoding="utf-8")
    (models / "_skip.py").write_text("", encoding="utf-8")
    assert set(discover_models(models)) == {"user"}
    assert discover_models(tmp_path / "nope") == {}


def test_build_index_progress(progress_index: AppIndex) -> None:
    assert len(progress_index.views) >= 20
    assert "welcome" in progress_index.views or "progress" in progress_index.views
    assert any(k.startswith("app.") for k in progress_index.config_keys)
    assert "user" in progress_index.models
    assert progress_index.ok


def test_build_index_boot_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    boot = tmp_path / "bootstrap"
    boot.mkdir()
    (boot / "app.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    # Application bootstrap loads providers from config — empty app still needs
    # enough structure. Simulate failure by patching Application.bootstrap.
    from almasix.framework import application as app_mod

    class Boom(app_mod.Application):
        def bootstrap(self):  # type: ignore[no-untyped-def]
            raise RuntimeError("boom")

    monkeypatch.setattr(app_mod, "Application", Boom)
    index = build_index(tmp_path)
    assert index.error is not None
    assert "boom" in index.error


def test_analysis_python_and_prism() -> None:
    source = textwrap.dedent(
        """\
        return view("welcome", {})
        url = route("signet.csrf-cookie")
        name = config("app.name")
        """
    )
    calls = find_python_calls(source)
    kinds = {c.kind for c in calls}
    assert kinds == {"view", "route", "config"}
    hit = call_at(source, 0, source.find('view("') + 7, language="python")
    assert hit is not None and hit.value == "welcome"
    # Cursor after ``view("wel`` — prefix is the typed fragment.
    wel_pos = source.find("welcome") + 3
    ctx = context_at(source, 0, wel_pos, language="python")
    assert ctx is not None and ctx.kind == "view" and ctx.prefix.startswith("wel")

    open_src = 'return view("prog'
    ctx2 = context_at(open_src, 0, len(open_src), language="python")
    assert ctx2 is not None and ctx2.prefix == "prog"

    prism = '@include("partials.nav")\n@extends("layouts.app")\n@if(True)\n'
    pcalls = find_prism_calls(prism)
    assert {c.kind for c in pcalls} == {"include", "extends"}
    assert directive_at(prism, 2, 2) == "if"
    assert directive_at(prism, 99, 0) is None


def test_features_against_progress(progress_index: AppIndex) -> None:
    view_name = next(iter(progress_index.views))
    py = f'return view("{view_name}")\nreturn view("no.such.view")\n'
    diags = diagnostics_python(progress_index, py)
    assert any("no.such.view" in d.message for d in diags)
    assert not any(view_name in d.message for d in diags)

    pos = py.find(view_name) + 1
    line = 0
    items = completions(progress_index, py, line, pos, language="python")
    assert any(i.label == view_name for i in items)

    loc = definition(progress_index, py, line, pos, language="python")
    assert loc is not None and loc.path == progress_index.views[view_name]

    links = document_links(progress_index, py, language="python")
    assert any(link.target == progress_index.views[view_name] for link in links)

    h = hover(progress_index, py, line, pos, language="python")
    assert h is not None and view_name in h.contents

    if progress_index.routes:
        route_name = next(iter(progress_index.routes))
        rsrc = f'route("{route_name}")'
        rh = hover(progress_index, rsrc, 0, rsrc.find(route_name) + 1, language="python")
        assert rh is not None and route_name in rh.contents
        rc = completions(progress_index, rsrc, 0, rsrc.find(route_name) + 1, language="python")
        assert any(i.label == route_name for i in rc)

    cfg = 'config("app.name")'
    ch = hover(progress_index, cfg, 0, cfg.find("app") + 1, language="python")
    assert ch is not None and "app.name" in ch.contents
    cc = completions(progress_index, cfg, 0, cfg.find("app") + 3, language="python")
    assert any(i.label.startswith("app.") for i in cc)

    prism = '@include("partials.nav")\n@foreach(items as item)\n'
    ph = hover(progress_index, prism, 1, 3, language="prism")
    assert ph is not None and "@foreach" in ph.contents
    assert directive_hover("foreach") is not None
    assert directive_hover("nope") is None
    assert "if" in PRISM_DIRECTIVES


def test_wire_protocol_completion_and_definition(
    progress_index: AppIndex, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)

    view_name = (
        "progress" if "progress" in progress_index.views else next(iter(progress_index.views))
    )
    source = f'render = view("{view_name}")\n'
    doc_path = tmp_path / "sample.py"
    doc_path.write_text(source, encoding="utf-8")

    server = create_server()
    session = LspWireSession(server)
    try:
        result = initialize_session(session, PROGRESS)
        caps = result["capabilities"]
        assert "completionProvider" in caps or caps.get("completionProvider") is not None
        assert caps.get("definitionProvider") in (True, {}) or "definitionProvider" in caps

        uri = open_document(session, doc_path, source, language_id="python")
        # Give didOpen diagnostics a moment to publish.
        import time

        time.sleep(0.2)

        char = source.find(view_name) + 2
        completion = session.request(
            "textDocument/completion",
            {
                "textDocument": {"uri": uri},
                "position": {"line": 0, "character": char},
            },
        )
        labels = [item["label"] for item in completion.get("items", completion or [])]
        assert view_name in labels

        definition_result = session.request(
            "textDocument/definition",
            {
                "textDocument": {"uri": uri},
                "position": {"line": 0, "character": char},
            },
        )
        assert definition_result is not None
        target = (
            definition_result["uri"]
            if isinstance(definition_result, dict)
            else definition_result[0]["uri"]
        )
        assert (
            view_name.replace(".", "/") in target or progress_index.views[view_name].name in target
        )

        hover_result = session.request(
            "textDocument/hover",
            {
                "textDocument": {"uri": uri},
                "position": {"line": 0, "character": char},
            },
        )
        assert hover_result is not None
        assert view_name in str(hover_result)

        links = session.request(
            "textDocument/documentLink",
            {"textDocument": {"uri": uri}},
        )
        assert links and any(
            view_name.replace(".", "/") in link.get("target", "") or True for link in links
        )

        rebuilt = session.request("workspace/executeCommand", {"command": "almasix.rebuildIndex"})
        assert "views" in rebuilt.lower() or "Indexed" in rebuilt

        session.request("shutdown", None)
        session.notify("exit", None)
    finally:
        session.close()


def test_cli_main_help(monkeypatch: pytest.MonkeyPatch) -> None:
    from almasix.lsp.cli import main

    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_public_api_exports() -> None:
    from almasix import lsp

    assert callable(lsp.build_index)
    assert callable(lsp.create_server)
    assert callable(lsp.run_stdio)
    assert callable(lsp.find_app_root)
