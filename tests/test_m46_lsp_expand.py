"""M46 expansion — route/config definition, translations, middleware, references, code actions."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from almasix.lsp import build_index, create_server
from almasix.lsp.analysis import context_at, find_python_calls
from almasix.lsp.features import (
    code_actions_create_view,
    completions,
    create_view_file,
    definition,
    diagnostics_python,
    find_view_references,
    references,
)
from almasix.lsp.index import (
    discover_route_locations,
    discover_translation_keys,
    fallback_route_file,
    view_path_for_name,
)
from tests.support import purge_generated_app_modules, without_base_path
from tests.support_lsp import LspWireSession, initialize_session, open_document

PROGRESS = Path(__file__).resolve().parents[1] / "examples" / "progress"


@pytest.fixture()
def progress_index(monkeypatch: pytest.MonkeyPatch):
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    index = build_index(PROGRESS)
    assert index.ok, index.error
    return index


def test_middleware_and_translations_indexed(progress_index) -> None:
    assert progress_index.has_lang
    assert "messages.welcome" in progress_index.translation_keys
    assert "auth" in progress_index.middleware_aliases
    assert "throttle" in progress_index.middleware_aliases
    assert len(progress_index.middleware_aliases) >= 10


def test_translation_and_middleware_completion(progress_index) -> None:
    src = '__( "messages.wel'
    ctx = context_at(src, 0, len(src), language="python")
    assert ctx is not None and ctx.kind == "trans"
    items = completions(progress_index, src, 0, len(src), language="python")
    assert any(i.label == "messages.welcome" for i in items)

    mw = '.middleware("aut'
    items2 = completions(progress_index, mw, 0, len(mw), language="python")
    assert any(i.label == "auth" for i in items2)


def test_translation_diagnostics_when_lang_present(progress_index) -> None:
    src = '__("messages.welcome")\n__("no.such.key")\n'
    diags = diagnostics_python(progress_index, src)
    assert any("no.such.key" in d.message for d in diags)
    assert not any("messages.welcome" in d.message for d in diags)


def test_config_and_route_definition(progress_index) -> None:
    cfg = 'config("app.name")'
    loc = definition(progress_index, cfg, 0, cfg.find("app") + 1, language="python")
    assert loc is not None
    assert loc.path.name == "app.py"

    # Named routes from the live app (signet / broadcasting) fall back to a routes file.
    if progress_index.routes:
        name = next(iter(progress_index.routes))
        rsrc = f'route("{name}")'
        rloc = definition(progress_index, rsrc, 0, rsrc.find(name) + 1, language="python")
        assert rloc is not None
        assert rloc.path.name.endswith(".py")


def test_route_locations_from_source(tmp_path: Path) -> None:
    routes = tmp_path / "routes"
    routes.mkdir()
    (routes / "web.py").write_text(
        'Route.get("/", home).name("home")\nRoute.get("/x", x, name="photos.index")\n',
        encoding="utf-8",
    )
    (routes / "api.py").write_text("# api\n", encoding="utf-8")
    locs = discover_route_locations(routes)
    assert "home" in locs and locs["home"][0].name == "web.py"
    assert "photos.index" in locs
    assert fallback_route_file(routes, "/api/users").name == "api.py"
    assert fallback_route_file(routes, "/welcome").name == "web.py"


def test_find_view_references(progress_index, tmp_path: Path) -> None:
    view_name = (
        "progress" if "progress" in progress_index.views else next(iter(progress_index.views))
    )
    # Seed a reference in a temp file under the app via extras.
    py = tmp_path / "ref.py"
    py.write_text(f'return view("{view_name}")\n', encoding="utf-8")
    refs = find_view_references(
        progress_index,
        view_name,
        extra_sources=[(py, py.read_text(encoding="utf-8"), "python")],
    )
    assert any(r.path == py for r in refs)

    src = f'view("{view_name}")'
    cursor_refs = references(
        progress_index, src, 0, src.find(view_name) + 1, language="python", document_path=py
    )
    assert cursor_refs


def test_code_action_create_view(
    progress_index, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Point base_path at a temp copy of views root by mutating index.
    progress_index.base_path = tmp_path
    (tmp_path / "resources" / "views").mkdir(parents=True)
    src = 'view("brand.new.page")'
    actions = code_actions_create_view(progress_index, src)
    assert actions and actions[0].view_name == "brand.new.page"
    create_view_file(actions[0].create_path)
    assert actions[0].create_path.is_file()
    assert view_path_for_name(tmp_path, "brand.new.page") == actions[0].create_path


def test_wire_references_and_code_action(
    progress_index, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)

    view_name = (
        "progress" if "progress" in progress_index.views else next(iter(progress_index.views))
    )
    source = textwrap.dedent(
        f"""\
        a = view("{view_name}")
        b = view("missing.view.xyz")
        """
    )
    doc = tmp_path / "wired.py"
    doc.write_text(source, encoding="utf-8")

    server = create_server()
    session = LspWireSession(server)
    try:
        initialize_session(session, PROGRESS)
        uri = open_document(session, doc, source, language_id="python")

        # definition for config via a second document
        cfg_src = 'x = config("app.name")\n'
        cfg_doc = tmp_path / "cfg.py"
        cfg_doc.write_text(cfg_src, encoding="utf-8")
        cfg_uri = open_document(session, cfg_doc, cfg_src, language_id="python")
        defn = session.request(
            "textDocument/definition",
            {
                "textDocument": {"uri": cfg_uri},
                "position": {"line": 0, "character": cfg_src.find("app") + 1},
            },
        )
        assert defn is not None
        assert "app.py" in (defn["uri"] if isinstance(defn, dict) else defn[0]["uri"])

        refs = session.request(
            "textDocument/references",
            {
                "textDocument": {"uri": uri},
                "position": {"line": 0, "character": source.find(view_name) + 1},
                "context": {"includeDeclaration": True},
            },
        )
        assert isinstance(refs, list) and len(refs) >= 1

        actions = session.request(
            "textDocument/codeAction",
            {
                "textDocument": {"uri": uri},
                "range": {
                    "start": {"line": 1, "character": source.splitlines()[1].find("missing")},
                    "end": {
                        "line": 1,
                        "character": source.splitlines()[1].find("missing") + 5,
                    },
                },
                "context": {"diagnostics": []},
            },
        )
        assert actions and any("Create view" in a.get("title", "") for a in actions)
        # Execute createView against a path under tmp so we don't dirty the example app.
        create_path = str(tmp_path / "resources" / "views" / "missing" / "view" / "xyz.prism.html")
        result = session.request(
            "workspace/executeCommand",
            {"command": "almasix.createView", "arguments": [create_path, "missing.view.xyz"]},
        )
        assert "Created" in result
        assert Path(create_path).is_file()

        session.request("shutdown", None)
        session.notify("exit", None)
    finally:
        session.close()


def test_discover_translation_keys_helpers(tmp_path: Path) -> None:
    lang = tmp_path / "lang"
    (lang / "en").mkdir(parents=True)
    (lang / "en" / "messages.py").write_text(
        'translations = {"hello": "Hi", "nested": {"a": "1"}}\n',
        encoding="utf-8",
    )
    (lang / "en.json").write_text('{"I love Almasix.": "x"}\n', encoding="utf-8")
    (lang / "en" / "messages.php").write_text(
        "<?php return ['farewell' => 'Bye'];\n",
        encoding="utf-8",
    )
    keys = discover_translation_keys(lang)
    assert "messages.hello" in keys
    assert "messages.nested.a" in keys
    assert "I love Almasix." in keys
    assert "messages.farewell" in keys
    assert discover_translation_keys(tmp_path / "missing") == ()


def test_middleware_call_detection() -> None:
    calls = find_python_calls('Route.get("/", x).middleware("auth")')
    assert any(c.kind == "middleware" and c.value == "auth" for c in calls)
