"""Directive snippet completions and route-name inserts."""

from __future__ import annotations

from pathlib import Path

import pytest

from almasix.lsp.analysis import context_at, directive_name_context_at, prism_helper_context_at
from almasix.lsp.directives import directive_snippet
from almasix.lsp.features import completions
from almasix.lsp.index import build_index
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


def test_directive_snippet_keeps_at_and_closes_blocks() -> None:
    assert directive_snippet("if") == "@if($1)\n    $0\n@endif"
    assert directive_snippet("foreach") == "@foreach($1)\n    $0\n@endforeach"
    assert directive_snippet("auth") == "@auth\n    $0\n@endauth"
    assert directive_snippet("csrf") == "@csrf"
    assert directive_snippet("route") == "@route('$1')"
    assert directive_snippet("extends") == "@extends('$1')"
    assert directive_snippet("endif") == "@endif"


def test_directive_snippet_bakes_line_indent() -> None:
    """Continuation lines include the opener's indent so @endif aligns in JetBrains."""
    assert directive_snippet("if", indent="    ") == ("@if($1)\n        $0\n    @endif")
    assert directive_snippet("auth", indent="  ") == "@auth\n      $0\n  @endauth"


def test_typing_at_if_offers_snippet_that_keeps_the_sigil(progress_index) -> None:
    """JetBrains treats ``@if`` as one token — the replace range must include ``@``."""
    source = "@if"
    ctx = directive_name_context_at(source, 0, 3)
    assert ctx is not None
    assert ctx.kind == "directive"
    assert ctx.prefix == "if"
    assert ctx.start_character == 0  # includes @

    items = completions(progress_index, source, 0, 3, language="prism-html")
    by_label = {item.label: item for item in items}
    assert "@if" in by_label
    assert "if" not in by_label  # bare name must not be offered
    item = by_label["@if"]
    assert item.insert_text == "@if($1)\n    $0\n@endif"
    assert item.insert_text_format == "snippet"
    assert item.start_character == 0
    assert item.end_character == 3


def test_indented_at_if_snippet_aligns_endif(progress_index) -> None:
    source = "    @if"
    items = completions(progress_index, source, 0, 7, language="prism-html")
    item = next(i for i in items if i.label == "@if")
    assert item.insert_text == "@if($1)\n        $0\n    @endif"
    assert item.start_character == 4


def test_ctrl_space_directive_snippets_include_at(progress_index) -> None:
    source = "<div>\n  \n</div>\n"
    items = completions(progress_index, source, 1, 2, language="prism-html")
    by_label = {item.label: item for item in items}
    assert "@foreach" in by_label
    assert by_label["@foreach"].insert_text.startswith("@foreach")
    assert "@endforeach" in by_label["@foreach"].insert_text
    assert by_label["@if"].insert_text.endswith("@endif")
    assert by_label["@if"].insert_text == "@if($1)\n      $0\n  @endif"


def test_format_document_uses_format_prism(progress_index) -> None:
    from almasix.lsp.features import format_document
    from almasix.prism.formatter import format_prism

    messy = "@if(True)\nx\n@endif\n"
    out = format_document(messy, language="prism-html")
    assert out == format_prism(messy)
    assert "    x" in (out or "")
    assert format_document("x = 1\n", language="python") is None


def test_route_names_inside_echo_and_after_bare_paren(progress_index) -> None:
    template = PROGRESS / "resources" / "views" / "welcome.prism.html"
    route_name = next(iter(progress_index.routes))

    quoted = "{{ route('') }}"
    char = quoted.index("('") + 2
    items = completions(
        progress_index,
        quoted,
        0,
        char,
        language="prism-html",
        uri_path=template,
    )
    labels = {item.label for item in items}
    assert route_name in labels
    assert all(item.insert_text == item.label for item in items)

    # ``route(`` / ``route()`` — replace the paren span with ``('name')``.
    bare = "{{ route() }}"
    bare_char = bare.index("(") + 1
    ctx = prism_helper_context_at(bare, 0, bare_char)
    assert ctx is not None
    assert ctx.kind == "route"
    assert ctx.wrap_quotes is True
    bare_items = completions(
        progress_index,
        bare,
        0,
        bare_char,
        language="prism-html",
        uri_path=template,
    )
    assert any(item.label == route_name for item in bare_items)
    chosen = next(item for item in bare_items if item.label == route_name)
    assert chosen.insert_text == f"('{route_name}')"
    assert chosen.start_character == bare.index("(")
    assert chosen.end_character == bare.index(")") + 1
    # Applying the edit must keep the surrounding echo braces.
    start, end = chosen.start_character, chosen.end_character
    assert bare[:start] + chosen.insert_text + bare[end:] == f"{{{{ route('{route_name}') }}}}"


def test_at_route_directive_then_route_names(progress_index) -> None:
    """Accepting ``@route`` inserts a quoted arg; names complete inside it."""
    source = "@rou"
    items = completions(progress_index, source, 0, 4, language="prism-html")
    route_item = next(item for item in items if item.label == "@route")
    assert route_item.insert_text == "@route('$1')"

    inside = "@route('')"
    char = inside.index("('") + 2
    ctx = context_at(inside, 0, char, language="prism-html")
    assert ctx is not None
    assert ctx.kind == "route"
    labels = {
        item.label for item in completions(progress_index, inside, 0, char, language="prism-html")
    }
    assert progress_index.routes
    assert labels & set(progress_index.routes)
