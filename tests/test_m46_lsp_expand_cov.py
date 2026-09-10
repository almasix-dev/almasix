"""Coverage fill for M46 expansions."""

from __future__ import annotations

from pathlib import Path

import pytest
from lsprotocol import types
from pygls.workspace import Workspace

from almasix.lsp import create_server
from almasix.lsp.features import (
    code_actions_create_view,
    create_view_file,
    definition,
    document_links,
    hover,
    references,
)
from almasix.lsp.index import (
    AppIndex,
    RouteInfo,
    _boot_application,
    _json_translation_keys,
    _load_py_dict,
    _php_translation_keys,
    _py_translation_keys,
    build_index,
    config_file_for_key,
    discover_config_files,
    discover_models,
    discover_route_locations,
    fallback_route_file,
)
from almasix.lsp.server import _ranges_overlap
from tests.support import purge_generated_app_modules, without_base_path

PROGRESS = Path(__file__).resolve().parents[1] / "examples" / "progress"


def test_fallback_route_file_branches(tmp_path: Path) -> None:
    assert fallback_route_file(tmp_path / "missing") is None
    routes = tmp_path / "routes"
    routes.mkdir()
    (routes / "api.py").write_text("#\n", encoding="utf-8")
    assert fallback_route_file(routes, "/api/x").name == "api.py"
    # no web.py — fall through to api then any
    assert fallback_route_file(routes, "/page").name == "api.py"
    (routes / "web.py").write_text("#\n", encoding="utf-8")
    assert fallback_route_file(routes, "/page").name == "web.py"
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "_skip.py").write_text("#\n", encoding="utf-8")
    (empty / "console.py").write_text("#\n", encoding="utf-8")
    assert fallback_route_file(empty, "/") is None


def test_translation_edge_cases(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert _json_translation_keys(bad) == set()
    arr = tmp_path / "arr.json"
    arr.write_text("[1,2]\n", encoding="utf-8")
    assert _json_translation_keys(arr) == set()

    lang = tmp_path / "lang"
    lang.mkdir()
    shallow = lang / "messages.py"
    shallow.write_text("translations = {'a': 'b'}\n", encoding="utf-8")
    assert _py_translation_keys(shallow, lang) == set()  # no locale segment
    shallow_php = lang / "alone.php"
    shallow_php.write_text("<?php return ['x' => 'y'];\n", encoding="utf-8")
    assert _php_translation_keys(shallow_php, lang) == set()

    broken = lang / "en"
    broken.mkdir()
    (broken / "bad.py").write_text("raise RuntimeError('x')\n", encoding="utf-8")
    assert _load_py_dict(broken / "bad.py") == {}
    assert _py_translation_keys(broken / "bad.py", lang) == set()

    # non-string keys skipped in flatten
    from almasix.lsp.index import _flatten_dict_keys

    assert _flatten_dict_keys({1: "x", "ok": "y"}) == ["ok"]

    # empty module — no recognized dict attrs
    empty = broken / "empty.py"
    empty.write_text("x = 1\n", encoding="utf-8")
    assert _load_py_dict(empty) == {}


def test_discover_helpers_empty(tmp_path: Path) -> None:
    assert discover_models(tmp_path / "no") == {}
    assert discover_config_files(tmp_path / "no") == {}
    assert discover_route_locations(tmp_path / "no") == {}
    assert config_file_for_key(AppIndex(base_path=tmp_path), "") is None


def test_hover_trans_middleware_and_links(progress_index_like) -> None:
    index = progress_index_like
    assert (
        "messages.welcome"
        in hover(index, '__("messages.welcome")', 0, 5, language="python").contents
    )  # type: ignore[union-attr]
    assert "not in lang" in hover(index, '__("nope")', 0, 5, language="python").contents  # type: ignore[union-attr]
    assert "alias" in hover(index, '.middleware("auth")', 0, 15, language="python").contents  # type: ignore[union-attr]
    assert "unknown alias" in hover(index, '.middleware("nope")', 0, 15, language="python").contents  # type: ignore[union-attr]

    links = document_links(
        index, 'route("signet.csrf-cookie")\nconfig("app.name")\n', language="python"
    )
    assert len(links) >= 1


def test_definition_misses(progress_index_like) -> None:
    index = progress_index_like
    assert definition(index, "x = 1", 0, 1, language="python") is None
    assert definition(index, 'view("nope")', 0, 7, language="python") is None
    assert definition(index, 'route("nope")', 0, 8, language="python") is None
    assert definition(index, '__("messages.welcome")', 0, 5, language="python") is None
    # route with missing path file
    index.routes["ghost"] = RouteInfo("ghost", "/", ("GET",), path=Path("/no/such.py"), line=0)
    assert definition(index, 'route("ghost")', 0, 8, language="python") is None


def test_references_and_code_action_edges(progress_index_like, tmp_path: Path) -> None:
    index = progress_index_like
    assert references(index, "x=1", 0, 1, language="python") == []
    assert references(index, 'route("x")', 0, 8, language="python") == []
    create_view_file(tmp_path / "a.prism.html")
    create_view_file(tmp_path / "a.prism.html")  # idempotent
    # code action skips non-unknown-view
    actions = code_actions_create_view(index, '__("no.such.key")')
    assert actions == []


def test_boot_application_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    boot = tmp_path / "bootstrap"
    boot.mkdir()
    (boot / "app.py").write_text("# no application attr\nx = 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    # Ensure only tmp is first on path and bootstrap is this stub.
    import sys
    import types

    monkeypatch.syspath_prepend(str(tmp_path))
    for key in list(sys.modules):
        if key == "bootstrap" or key.startswith("bootstrap."):
            del sys.modules[key]

    stub = types.ModuleType("bootstrap.app")
    # no .application
    monkeypatch.setattr(
        "importlib.import_module",
        lambda name: stub if name == "bootstrap.app" else __import__(name),
    )
    app = _boot_application(tmp_path)
    assert app is not None
    assert hasattr(app, "bootstrap") or hasattr(app, "router")


def test_code_action_overlap_and_non_python(tmp_path: Path) -> None:
    ls = create_server()
    ls.protocol._workspace = Workspace(None, types.TextDocumentSyncKind.Full, [], None)
    ls.protocol._workspace.put_text_document(
        types.TextDocumentItem(
            uri="file:///tmp/x.prism.html",
            language_id="prism",
            version=1,
            text="@if(True)\n",
        )
    )
    handler = ls.protocol.fm.features[types.TEXT_DOCUMENT_CODE_ACTION]
    result = handler(
        types.CodeActionParams(
            text_document=types.TextDocumentIdentifier(uri="file:///tmp/x.prism.html"),
            range=types.Range(
                start=types.Position(line=0, character=0),
                end=types.Position(line=0, character=1),
            ),
            context=types.CodeActionContext(diagnostics=[]),
        )
    )
    assert result == []

    assert _ranges_overlap(
        types.Range(
            start=types.Position(line=1, character=0),
            end=types.Position(line=1, character=5),
        ),
        1,
        0,
        1,
        10,
    )
    assert not _ranges_overlap(
        types.Range(
            start=types.Position(line=0, character=0),
            end=types.Position(line=0, character=1),
        ),
        2,
        0,
        2,
        5,
    )


def test_create_view_command_via_handler(tmp_path: Path) -> None:
    ls = create_server()
    path = tmp_path / "v.prism.html"
    result = ls.protocol.fm.commands["almasix.createView"](str(path), "v")
    assert "Created" in result
    assert path.is_file()
    # missing path arg style — only path
    path2 = tmp_path / "w.prism.html"
    result2 = ls.protocol.fm.commands["almasix.createView"](str(path2))
    assert path2.is_file()
    assert "Created" in result2


def test_more_coverage_edges(
    progress_index_like, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = progress_index_like

    # config definition when file missing from map
    bare = AppIndex(base_path=tmp_path, config_files={})
    assert definition(bare, 'config("app.name")', 0, 10, language="python") is None

    # document links skip unknown route/config
    assert document_links(index, 'route("nope")\nconfig("zzz.nope")\n', language="python") == []

    # duplicate reference suppression
    view_name = next(iter(index.views))
    py = tmp_path / "dup.py"
    text = f'view("{view_name}")\n'
    py.write_text(text, encoding="utf-8")
    from almasix.lsp.features import find_view_references

    refs = find_view_references(
        index,
        view_name,
        extra_sources=[(py, text, "python"), (py, text, "python")],
    )
    assert sum(1 for r in refs if r.path == py) == 1

    # walk real app for references (hits pruned source walk)
    many = find_view_references(index, view_name)
    assert many

    # Monorepo-shaped root with a decoy node_modules must not hang or explode.
    decoy = tmp_path / "monorepo"
    (decoy / "app").mkdir(parents=True)
    (decoy / "node_modules" / "left-pad").mkdir(parents=True)
    (decoy / "node_modules" / "left-pad" / "index.js").write_text("x", encoding="utf-8")
    (decoy / "website" / "node_modules" / "x").mkdir(parents=True)
    (decoy / "app" / "hit.py").write_text(f'view("{view_name}")\n', encoding="utf-8")
    decoy_index = AppIndex(base_path=decoy, views=dict(index.views))
    decoy_refs = find_view_references(decoy_index, view_name)
    assert any(r.path.name == "hit.py" for r in decoy_refs)

    # references without document_path
    src = f'view("{view_name}")'
    assert references(index, src, 0, src.find(view_name) + 1, language="python")

    # fallback only other.py
    routes = tmp_path / "r2"
    routes.mkdir()
    (routes / "other.py").write_text("#\n", encoding="utf-8")
    assert fallback_route_file(routes, "/x").name == "other.py"

    # py load via stem attribute
    lang = tmp_path / "lang2" / "en"
    lang.mkdir(parents=True)
    f = lang / "custom.py"
    f.write_text("custom = {'k': 'v'}\n", encoding="utf-8")
    assert "k" in _load_py_dict(f)

    # boot failure path
    monkeypatch.setattr(
        "almasix.lsp.index._boot_application",
        lambda root: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    failed = build_index(tmp_path)
    # tmp_path has no bootstrap — find via explicit base still calls boot
    (tmp_path / "bootstrap").mkdir(exist_ok=True)
    (tmp_path / "bootstrap" / "app.py").write_text("x=1\n", encoding="utf-8")
    failed = build_index(tmp_path)
    assert failed.error and "boom" in failed.error

    # route with source location (loc is not None) during build_index
    def fake_locs(d):
        locs = discover_route_locations(d)
        locs["signet.csrf-cookie"] = (PROGRESS / "routes" / "web.py", 5)
        return locs

    monkeypatch.undo()  # drop boom patch from earlier
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    monkeypatch.setattr("almasix.lsp.index.discover_route_locations", fake_locs)
    indexed = build_index(PROGRESS)
    assert indexed.routes["signet.csrf-cookie"].line == 5

    # code action range no overlap on server
    ls = create_server()
    ls.index = index
    ls.protocol._workspace = Workspace(None, types.TextDocumentSyncKind.Full, [], None)
    uri = "file:///tmp/miss.py"
    src2 = 'view("totally.missing.view")\n'
    ls.protocol._workspace.put_text_document(
        types.TextDocumentItem(uri=uri, language_id="python", version=1, text=src2)
    )
    actions = ls.protocol.fm.features[types.TEXT_DOCUMENT_CODE_ACTION](
        types.CodeActionParams(
            text_document=types.TextDocumentIdentifier(uri=uri),
            range=types.Range(
                start=types.Position(line=5, character=0),
                end=types.Position(line=5, character=1),
            ),
            context=types.CodeActionContext(diagnostics=[]),
        )
    )
    assert actions == []


def test_branch_partials(tmp_path: Path) -> None:
    # /api URI but only web.py present
    routes = tmp_path / "routes"
    routes.mkdir()
    (routes / "web.py").write_text("#\n", encoding="utf-8")
    assert fallback_route_file(routes, "/api/x").name == "web.py"
    assert fallback_route_file(routes, "api/x").name == "web.py"

    # lang walk skips junk files
    lang = tmp_path / "lang"
    lang.mkdir()
    (lang / "notes.txt").write_text("x", encoding="utf-8")
    (lang / ".hidden.json").write_text("{}", encoding="utf-8")
    from almasix.lsp.index import discover_translation_keys

    assert discover_translation_keys(lang) == ()

    # models skip underscore
    models = tmp_path / "models"
    models.mkdir()
    (models / "_base.py").write_text("x=1\n", encoding="utf-8")
    (models / "user.py").write_text("x=1\n", encoding="utf-8")
    assert set(discover_models(models)) == {"user"}


@pytest.fixture()
def progress_index_like(monkeypatch: pytest.MonkeyPatch):
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    index = build_index(PROGRESS)
    assert index.ok, index.error
    return index
