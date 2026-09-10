"""M46 depth — Prism template variable index + echo completion / definition."""

from __future__ import annotations

from pathlib import Path

import pytest

from almasix.lsp.analysis import (
    prism_helper_call_at,
    prism_helper_context_at,
    template_var_at,
    template_var_context_at,
)
from almasix.lsp.features import completions, definition, hover
from almasix.lsp.index import build_index
from almasix.lsp.view_context import (
    ViewVarInfo,
    discover_vite_entries,
    merge_vars_for_view,
)
from tests.support import purge_generated_app_modules, without_base_path

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


def test_discover_welcome_view_keys() -> None:
    from almasix.lsp.view_context import discover_view_data_keys

    data = discover_view_data_keys(PROGRESS)
    assert "welcome" in data
    assert "app_name" in data["welcome"]
    assert "features" in data["welcome"]
    info = data["welcome"]["app_name"]
    assert info.path is not None
    assert info.path.name == "welcome_controller.py"


def test_build_index_includes_view_context(progress_index) -> None:
    assert progress_index.view_helpers
    assert "csrf_token" in progress_index.view_shared
    assert "app_name" in progress_index.view_data.get("welcome", {})
    assert progress_index.vite_entries


def test_echo_completion_and_definition(progress_index) -> None:
    template = PROGRESS / "resources" / "views" / "welcome.prism.html"
    source = "<h1>{{ app_name }}</h1>\n@if(features)\n<p>ok</p>\n@endif\n"
    line0 = source.splitlines()[0]
    char = line0.index("app_name") + 3
    ctx = template_var_context_at(source, 0, char)
    assert ctx is not None
    assert ctx.kind == "var"
    assert ctx.prefix.startswith("app")

    items = completions(
        progress_index,
        source,
        0,
        char,
        language="prism-html",
        uri_path=template,
    )
    labels = {i.label for i in items}
    assert "app_name" in labels

    open_char = line0.index("{{") + 3
    wide = completions(
        progress_index,
        source,
        0,
        open_char,
        language="prism-html",
        uri_path=template,
    )
    wide_labels = {i.label for i in wide}
    assert "app_name" in wide_labels
    assert "csrf_token" in wide_labels or "url" in wide_labels

    ref = template_var_at(source, 0, char)
    assert ref is not None
    assert ref.name == "app_name"

    loc = definition(
        progress_index,
        source,
        0,
        char,
        language="prism-html",
        uri_path=template,
    )
    assert loc is not None
    assert loc.path.name == "welcome_controller.py"

    tip = hover(
        progress_index,
        source,
        0,
        char,
        language="prism-html",
        uri_path=template,
    )
    assert tip is not None
    assert "app_name" in tip.contents


def test_echo_helper_route_and_vite(progress_index) -> None:
    template = PROGRESS / "resources" / "views" / "welcome.prism.html"
    route_name = next(iter(progress_index.routes))
    vite_key = next(
        (k for k in progress_index.vite_entries if "resources/js" in k or k.endswith(".js")),
        next(iter(progress_index.vite_entries)),
    )
    source = f'{{{{ route("{route_name}") }}}} {{{{ vite("{vite_key}") }}}} {{{{ url }}}}'
    # route string
    route_char = source.index(route_name) + 1
    ctx = prism_helper_context_at(source, 0, route_char)
    assert ctx is not None
    assert ctx.kind == "route"
    call = prism_helper_call_at(source, 0, route_char)
    assert call is not None
    assert call.value == route_name
    loc = definition(
        progress_index,
        source,
        0,
        route_char,
        language="prism-html",
        uri_path=template,
    )
    assert loc is not None

    # vite path
    vite_char = source.index(vite_key) + min(2, len(vite_key) // 2)
    vctx = prism_helper_context_at(source, 0, vite_char)
    assert vctx is not None
    assert vctx.kind == "vite"
    vloc = definition(
        progress_index,
        source,
        0,
        vite_char,
        language="prism-html",
        uri_path=template,
    )
    assert vloc is not None

    # bare helper name url
    url_char = source.rindex("url") + 1
    uloc = definition(
        progress_index,
        source,
        0,
        url_char,
        language="prism-html",
        uri_path=template,
    )
    assert uloc is not None
    assert uloc.path.name == "url.py"


def test_route_completion_on_an_empty_argument(progress_index) -> None:
    """Typing ``route('')`` must offer route names before anything is typed."""
    template = PROGRESS / "resources" / "views" / "welcome.prism.html"
    route_name = next(iter(progress_index.routes))

    for source in (
        "<a href=\"{{ route('') }}\">go</a>",  # inside an echo
        "@route('')",  # directive form
        "@if(route_is(''))",  # directive argument
    ):
        char = source.index("('") + 2
        ctx = prism_helper_context_at(source, 0, char)
        assert ctx is not None, source
        assert ctx.kind == "route", source
        assert ctx.prefix == "", source
        labels = {
            item.label
            for item in completions(
                progress_index,
                source,
                0,
                char,
                language="prism-html",
                uri_path=template,
            )
        }
        assert route_name in labels, source


def test_ctrl_space_in_plain_markup_offers_the_prism_surface(progress_index) -> None:
    """An explicit invoke outside any island still has directives and globals."""
    template = PROGRESS / "resources" / "views" / "welcome.prism.html"
    source = '<div class="card">\n  \n</div>\n'

    items = completions(
        progress_index,
        source,
        1,
        2,
        language="prism-html",
        uri_path=template,
    )
    labels = {item.label for item in items}
    assert "@if" in labels
    assert "@foreach" in labels
    assert "app_name" in labels or "url" in labels


def test_discover_vite_entries() -> None:
    entries = discover_vite_entries(PROGRESS)
    assert any("app" in key or "resources/js" in key for key in entries)


def test_merge_vars_data_overrides_helper() -> None:
    helpers = [
        ViewVarInfo(name="action", kind="helper", detail="URL helper"),
    ]
    data = {
        "form": {
            "action": ViewVarInfo(
                name="action",
                kind="data",
                detail="Passed to view",
                path=Path("/tmp/x.py"),
                line=1,
                view="form",
            )
        }
    }
    merged = merge_vars_for_view("form", view_data=data, helpers=helpers, shared={})
    assert merged["action"].kind == "data"


def test_view_dict_regex_fallback_and_name_lookup(tmp_path: Path) -> None:
    from almasix.lsp.view_context import (
        _extract_view_dict_keys_regex,
        auth_shared_vars,
        builtin_helpers,
        view_name_for_template,
    )

    broken = "view('board', {'title': x +})\n"  # intentionally invalid Python
    keys = _extract_view_dict_keys_regex(broken)
    assert ("board", "title", 0) in keys

    template = tmp_path / "welcome.prism.html"
    template.write_text("<p></p>", encoding="utf-8")
    assert view_name_for_template({"welcome": template}, template) == "welcome"
    assert view_name_for_template({"welcome": template}, tmp_path / "other.prism.html") is None

    helpers = {info.name for info in builtin_helpers()}
    assert "csrf_token" in helpers or "route" in helpers
    shared = {info.name for info in auth_shared_vars()}
    assert "csrf_token" in shared or "errors" in shared or shared
