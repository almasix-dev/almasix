"""Extra coverage for almasix.lsp edge paths."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from lsprotocol import types

from almasix.lsp import create_server, run_stdio
from almasix.lsp.analysis import (
    CursorContext,
    _open_string_context,
    call_at,
    context_at,
    find_calls,
    find_python_calls,
)
from almasix.lsp.cli import main as cli_main
from almasix.lsp.commands.serve import LspServeCommand
from almasix.lsp.features import (
    completions,
    completions_for_context,
    definition,
    diagnostics_python,
    document_links,
    hover,
)
from almasix.lsp.index import AppIndex, RouteInfo, discover_views
from almasix.lsp.server import (
    AlmasixLanguageServer,
    _completion_kind,
    _language_id,
    _publish_diagnostics,
    _resolve_workspace_root,
    _safe_build_index,
)
from tests.support import purge_generated_app_modules, without_base_path
from tests.support_lsp import LspWireSession, initialize_session, open_document

PROGRESS = Path(__file__).resolve().parents[1] / "examples" / "progress"


def test_run_stdio_and_create_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("almasix.lsp.cli.main", lambda argv=None: 0)
    assert run_stdio() == 0
    assert isinstance(create_server(), AlmasixLanguageServer)


def test_cli_main_starts_io(monkeypatch: pytest.MonkeyPatch) -> None:
    started: dict[str, bool] = {}

    class Fake:
        def start_io(self) -> None:
            started["ok"] = True

    monkeypatch.setattr("almasix.lsp.server.create_server", lambda: Fake())
    assert cli_main([]) == 0
    assert started["ok"] is True


def test_cli_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def guarded(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "almasix.lsp.server" and fromlist:
            raise ImportError("missing lsp deps")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert cli_main([]) == 1


def test_lsp_serve_command_ok_and_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    cmd = LspServeCommand()
    messages: list[str] = []
    cmd.info = lambda m: messages.append(str(m))  # type: ignore[method-assign]
    cmd.error = lambda m: messages.append(str(m))  # type: ignore[method-assign]
    cmd.line = lambda m: messages.append(str(m))  # type: ignore[method-assign]

    class Fake:
        def start_io(self) -> None:
            messages.append("started")

    monkeypatch.setattr("almasix.lsp.server.create_server", lambda: Fake())
    assert cmd.handle() == 0

    import builtins

    real_import = builtins.__import__

    def guarded(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "almasix.lsp.server":
            raise ImportError("missing")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded)
    cmd2 = LspServeCommand()
    cmd2.error = lambda m: messages.append(str(m))  # type: ignore[method-assign]
    cmd2.line = lambda m: messages.append(str(m))  # type: ignore[method-assign]
    assert cmd2.handle() == 1
    assert any("almasix[lsp]" in m for m in messages)


def test_analysis_edge_branches() -> None:
    assert find_calls("view('x')", language="python")
    assert find_calls("@include('x')", language="prism")
    assert find_calls("view('x')\n@include('y')", language="plaintext")
    both = find_calls("view('x')", language="unknown")
    assert both

    assert call_at("x = 1", 0, 1, language="python") is None
    assert context_at("x = 1", 0, 1, language="python") is None
    assert context_at("x = 1", 5, 0, language="python") is None

    calls = find_python_calls('view("ab")')
    c = calls[0]
    assert call_at('view("ab")', c.start_line, c.start_character - 1, language="python") is None
    assert call_at('view("ab")', c.end_line, c.end_character + 1, language="python") is None

    line = "@include('par"
    ctx = _open_string_context(line, 0, len(line), language="prism")
    assert ctx is not None and ctx.kind == "include"
    assert _open_string_context('config("app', 0, 11, language="python") is not None
    assert _open_string_context("hi", 0, 2, language="python") is None
    assert _open_string_context("hi", 9, 0, language="python") is None


def test_features_edge_branches() -> None:
    index = AppIndex(
        base_path=Path("."),
        views={"welcome": Path("/tmp/welcome.prism.html")},
        routes={"home": RouteInfo("home", "/", ("GET",))},
        config_keys=("app.name",),
    )
    assert completions(index, "x", 0, 0, language="python") == []
    assert (
        completions_for_context(
            index,
            CursorContext(
                kind="view",
                prefix="zzz",
                start_line=0,
                start_character=0,
                end_line=0,
                end_character=0,
            ),
        )
        == []
    )

    src = 'view("missing")\nroute("missing")\nconfig("nope")\n'
    assert "Not found" in hover(index, src, 0, 7, language="python").contents  # type: ignore[union-attr]
    assert "Unknown" in hover(index, src, 1, 8, language="python").contents  # type: ignore[union-attr]
    assert "not in config" in hover(index, src, 2, 9, language="python").contents  # type: ignore[union-attr]
    assert definition(index, src, 0, 7, language="python") is None
    assert definition(index, 'route("home")', 0, 8, language="python") is None
    assert document_links(index, 'route("home")', language="python") == []
    assert diagnostics_python(index, 'route("x")') == []
    assert hover(index, "@unknown(1)\n", 0, 3, language="prism") is None
    assert hover(index, "plain", 0, 0, language="prism") is None


def test_remaining_branches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from pygls.workspace import Workspace

    from almasix.lsp.analysis import StringCall, _prefix_before_cursor, directive_at
    from almasix.lsp.features import _filter_prefix, _hover_for_call

    assert _filter_prefix(["a", "b"], "") == ["a", "b"]
    assert [
        i.label
        for i in completions_for_context(
            AppIndex(base_path=Path("."), views={"welcome": Path("w")}),
            CursorContext(
                kind="view",
                prefix="",
                start_line=0,
                start_character=0,
                end_line=0,
                end_character=0,
            ),
        )
    ] == ["welcome"]

    forged = CursorContext(
        kind="view",
        prefix="",
        start_line=0,
        start_character=0,
        end_line=0,
        end_character=0,
    )
    object.__setattr__(forged, "kind", "nope")
    assert completions_for_context(AppIndex(base_path=Path(".")), forged) == []

    call = StringCall(
        kind="view",
        value="welcome",
        start_line=0,
        start_character=0,
        end_line=0,
        end_character=7,
        start_offset=0,
        end_offset=7,
    )
    assert _prefix_before_cursor("welcome", call, 99, 0) == "welcome"
    call2 = StringCall(
        kind="view",
        value="ab",
        start_line=0,
        start_character=5,
        end_line=0,
        end_character=7,
        start_offset=5,
        end_offset=7,
    )
    assert _prefix_before_cursor("view(ab)", call2, 0, 3) == ""
    # Multi-line offset accumulation (line 1).
    multi = 'aaa\nview("ab")'
    calls = find_python_calls(multi)
    assert calls
    ctx = context_at(multi, 1, calls[0].start_character + 1, language="python")
    assert ctx is not None

    assert directive_at("@if\n", 0, 50) is None
    assert directive_at("no directive here", 0, 2) is None
    assert _open_string_context('view("x', 0, 7, language="ruby") is not None

    index = AppIndex(base_path=Path("."))
    weird = StringCall(
        kind="view",
        value="x",
        start_line=0,
        start_character=0,
        end_line=0,
        end_character=1,
        start_offset=0,
        end_offset=1,
    )
    object.__setattr__(weird, "kind", "nope")
    assert _hover_for_call(index, weird) is None

    with patch("almasix.lsp.features._hover_for_call", return_value=None):
        assert hover(index, 'view("x")', 0, 7, language="python") is None

    # Direct handlers: initialized error + rebuild error + did_save no root
    ls = create_server()
    ls.index = AppIndex(base_path=tmp_path, error="boot failed")
    ls.protocol.fm.features[types.INITIALIZED](types.InitializedParams())

    ls._workspace_root = None
    monkeypatch.setattr("almasix.lsp.server.find_app_root", lambda start=None: None)
    ls.index = AppIndex(base_path=tmp_path, error="still bad")
    rebuilt = ls.protocol.fm.commands["almasix.rebuildIndex"]([])
    assert (
        "bootstrap" in rebuilt.lower()
        or "still bad" in rebuilt.lower()
        or "no almasix" in rebuilt.lower()
    )

    ls.protocol._workspace = Workspace(None, types.TextDocumentSyncKind.Full, [], None)
    ls.protocol._workspace.put_text_document(
        types.TextDocumentItem(
            uri="file:///tmp/x.py", language_id="python", version=1, text='view("nope")'
        )
    )
    published: list[object] = []
    ls.text_document_publish_diagnostics = lambda p: published.append(p)  # type: ignore[method-assign]
    ls.protocol.fm.features[types.TEXT_DOCUMENT_DID_SAVE](
        types.DidSaveTextDocumentParams(
            text_document=types.TextDocumentIdentifier(uri="file:///tmp/x.py")
        )
    )
    assert published

    # Non-python diagnostics clear
    ls.protocol._workspace.put_text_document(
        types.TextDocumentItem(
            uri="file:///tmp/y.prism.html",
            language_id="prism",
            version=1,
            text="@if(True)\n",
        )
    )
    _publish_diagnostics(ls, "file:///tmp/y.prism.html")

    # Progress begin ok / end raises
    ls.protocol.progress = MagicMock()
    ls.protocol.progress.begin.side_effect = None
    ls.protocol.progress.end.side_effect = RuntimeError("end fail")
    assert isinstance(_safe_build_index(ls, tmp_path), AppIndex)
    ls.protocol.progress.begin.side_effect = RuntimeError("no")
    assert isinstance(_safe_build_index(ls, tmp_path), AppIndex)

    assert _language_id(SimpleNamespace(language_id="python")) == "python"
    assert _language_id(SimpleNamespace()) == "plaintext"
    assert _completion_kind("view") == types.CompletionItemKind.File
    assert _completion_kind("route") == types.CompletionItemKind.Reference
    assert _completion_kind("config") == types.CompletionItemKind.Value
    assert _completion_kind("other") == types.CompletionItemKind.Text

    # Restore real find_app_root for resolve tests.
    monkeypatch.undo()

    monkeypatch.chdir(tmp_path)
    assert (
        _resolve_workspace_root(types.InitializeParams(capabilities=types.ClientCapabilities()))
        is None
    )
    assert (
        _resolve_workspace_root(
            types.InitializeParams(
                capabilities=types.ClientCapabilities(),
                root_path=str(tmp_path),
            )
        )
        == tmp_path.resolve()
    )
    assert (
        _resolve_workspace_root(
            types.InitializeParams(
                capabilities=types.ClientCapabilities(),
                root_uri=f"file://{tmp_path}",
            )
        )
        == tmp_path.resolve()
    )

    without_base_path(monkeypatch)
    purge_generated_app_modules()
    assert (
        _resolve_workspace_root(
            types.InitializeParams(
                capabilities=types.ClientCapabilities(),
                root_path=str(PROGRESS),
            )
        )
        == PROGRESS.resolve()
    )
    assert (
        _resolve_workspace_root(
            types.InitializeParams(
                capabilities=types.ClientCapabilities(),
                root_uri=f"file://{PROGRESS}",
            )
        )
        == PROGRESS.resolve()
    )
    assert (
        _resolve_workspace_root(
            types.InitializeParams(
                capabilities=types.ClientCapabilities(),
                workspace_folders=[
                    types.WorkspaceFolder(uri=f"file://{PROGRESS}", name="progress")
                ],
            )
        )
        == PROGRESS.resolve()
    )


def test_wire_did_change_save_hover_prism(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)

    server = create_server()
    session = LspWireSession(server)
    try:
        init = initialize_session(session, PROGRESS)
        assert init.get("serverInfo", {}).get("name") == "almasix-lsp"

        prism = tmp_path / "nav.prism.html"
        text = '@include("partials.nav")\n@foreach(xs as x)\n'
        prism.write_text(text, encoding="utf-8")
        uri = open_document(session, prism, text, language_id="prism")

        hover_result = session.request(
            "textDocument/hover",
            {"textDocument": {"uri": uri}, "position": {"line": 1, "character": 3}},
        )
        assert hover_result is not None

        session.notify(
            "textDocument/didChange",
            {
                "textDocument": {"uri": uri, "version": 2},
                "contentChanges": [{"text": text + "\n"}],
            },
        )
        session.notify("textDocument/didSave", {"textDocument": {"uri": uri}})

        py = tmp_path / "miss.py"
        py_src = "x = 1\n"
        py.write_text(py_src, encoding="utf-8")
        uri2 = open_document(session, py, py_src, language_id="python")
        assert (
            session.request(
                "textDocument/completion",
                {
                    "textDocument": {"uri": uri2},
                    "position": {"line": 0, "character": 1},
                },
            )["items"]
            == []
        )
        assert (
            session.request(
                "textDocument/definition",
                {
                    "textDocument": {"uri": uri2},
                    "position": {"line": 0, "character": 1},
                },
            )
            is None
        )
        # hover miss
        assert (
            session.request(
                "textDocument/hover",
                {
                    "textDocument": {"uri": uri2},
                    "position": {"line": 0, "character": 1},
                },
            )
            is None
        )
        session.request("shutdown", None)
        session.notify("exit", None)
    finally:
        session.close()


def test_discover_views_skips_directories(tmp_path: Path) -> None:
    root = tmp_path / "views"
    root.mkdir()
    (root / "x.prism.html").mkdir()
    assert discover_views(root) == {}


def test_main_module_importable() -> None:
    mod = importlib.import_module("almasix.lsp.__main__")
    assert callable(mod.main)
