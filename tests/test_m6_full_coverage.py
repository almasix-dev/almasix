"""Drive almasix.prism to 100% statement/branch coverage where reachable."""

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from almasix.prism.compiler import (
    _compile_child,
    _split_slots,
    _tag_kind,
    compile_template,
)
from almasix.prism.component import Component
from almasix.prism.engine import Engine
from almasix.prism.xtags import _parse_attrs, expand_x_tags


def test_balanced_paren_escape_in_string() -> None:
    render = compile_template(r'@if("a\"b" == "a\"b")Y@endif')
    assert render({}, None) == "Y"


def test_custom_directive_before_builtin_and_bare() -> None:
    """extra_match can win ordering; bare custom directives skip balanced scan."""
    render = compile_template(
        "@mark@if(True)Y@endif",
        directives={"mark": lambda expr: "__w('M')"},
    )
    assert render({}, None) == "MY"


def test_balanced_always_requires_parens() -> None:
    with pytest.raises(SyntaxError, match="requires"):
        compile_template("@if True\nY\n@endif")


def test_extends_errors_and_implicit_content(tmp_path: Path) -> None:
    views = tmp_path / "views"
    (views / "layouts").mkdir(parents=True)
    (views / "layouts" / "app.prism.html").write_text(
        "@yield('content')",
        encoding="utf-8",
    )
    (views / "implicit.prism.html").write_text(
        "@extends('layouts.app')\nHello",
        encoding="utf-8",
    )
    assert "Hello" in Engine(paths=[views]).render("implicit")

    with pytest.raises(SyntaxError, match="top level"):
        compile_template("@section('a')\n@extends('layouts.app')\n@endsection")
    with pytest.raises(SyntaxError, match="cannot nest"):
        compile_template("@section('a')\n@section('b', 'v')\n@endsection")
    with pytest.raises(SyntaxError, match="Unexpected"):
        compile_template("@endsection")
    with pytest.raises(SyntaxError, match="Nested"):
        compile_template(
            "@section('a')\n@section('b')\nx\n@endsection\n@endsection"
        )


def test_unknown_tag_kind() -> None:
    with pytest.raises(SyntaxError, match="Unknown"):
        _tag_kind(SimpleNamespace(group=lambda _n=0: "@notareal"))


def test_section_override_string_and_zero_arg(tmp_path: Path) -> None:
    views = tmp_path / "views"
    views.mkdir()
    (views / "p.prism.html").write_text("@yield('content')", encoding="utf-8")
    mid = _compile_child("p", {"content": "MID"}, name="mid")
    engine = Engine(paths=[views])
    assert mid({"__sections": {"content": "plain"}}, engine) == "plain"
    assert mid({"__sections": {"content": lambda: "zero"}}, engine) == "zero"
    assert mid({"__sections": {"content": lambda c, e: "two"}}, engine) == "two"


def test_python_mode_keeps_inner_tags() -> None:
    # @csrf has no required paren; it is captured into the python buffer.
    render = compile_template("@python\nx = '@csrf'\n@endpython{{ x }}")
    assert render({}, None) == "@csrf"


def test_push_and_slot_scan_skips_inner_tags() -> None:
    """Depth scanners must ignore unrelated tags (branch coverage)."""
    render = compile_template(
        "@push('s'){{ v }}@parent@endpush@stack('s')"
    )
    assert "X" in render({"v": "X"}, Engine(paths=[]))

    default, named = _split_slots("@slot('a'){{ v }}@endslot\nD")
    assert "D" in default
    assert "{{ v }}" in named["a"]

    with pytest.raises(SyntaxError, match="Unclosed @component"):
        compile_template("@component('a')\nbody")
    with pytest.raises(SyntaxError, match="Unclosed @push"):
        compile_template("@push('s')\nbody")
    with pytest.raises(SyntaxError, match="Unclosed @cache"):
        compile_template("@cache('k')\nbody")

    # Word-boundary: do not glue letters onto @endpush / @endcache.
    nested_push = compile_template(
        "@push('s')@push('t')T@endpush P@endpush@stack('s')@stack('t')"
    )
    out = nested_push({}, Engine(paths=[]))
    assert "P" in out and "T" in out

    nested_cache = compile_template(
        "@cache('outer')@cache('inner')Z@endcache@endcache"
    )
    assert "Z" in nested_cache({}, Engine(paths=[]))


def test_elseif_chain() -> None:
    render = compile_template("@if(False)A@elseif(True)B@else C@endif")
    assert render({}, None) == "B"


def test_each_without_empty_view(tmp_path: Path) -> None:
    views = tmp_path / "views"
    views.mkdir()
    (views / "row.prism.html").write_text("{{ item }}", encoding="utf-8")
    (views / "page.prism.html").write_text(
        "@each('row', items, 'item')",
        encoding="utf-8",
    )
    engine = Engine(paths=[views])
    assert engine.render("page", {"items": ["a"]}) == "a"
    assert engine.render("page", {"items": []}) == ""


def test_nested_named_slots(tmp_path: Path) -> None:
    default, named = _split_slots(
        "@slot('inner')\n@slot('deep')D@endslot\nI\n@endslot\nO\n"
    )
    assert "O" in default
    assert list(named) == ["inner"]
    assert "@slot('deep')" in named["inner"]
    assert "D" in named["inner"]
    assert "I" in named["inner"]

    views = tmp_path / "views"
    (views / "components").mkdir(parents=True)
    (views / "components" / "outer.prism.html").write_text(
        "<o>{{ slot }}{{ inner }}</o>",
        encoding="utf-8",
    )
    (views / "page.prism.html").write_text(
        """
@component('outer')
@slot('inner')INNER@endslot
O
@endcomponent
""".strip(),
        encoding="utf-8",
    )
    html = Engine(paths=[views]).render("page")
    assert "O" in html
    assert "INNER" in html


def test_dedent_python_trailing_and_empty() -> None:
    empty = compile_template("@python\n\n\n@endpython\nE")
    assert "E" in empty({}, None)
    trailing = compile_template("@python\npass\n\n@endpython\nT")
    assert "T" in trailing({}, None)


def test_include_arg_errors() -> None:
    with pytest.raises(SyntaxError, match="string literal"):
        compile_template("@include(bare)")
    with pytest.raises(SyntaxError, match="string literal"):
        compile_template("@include()")
    with pytest.raises(SyntaxError, match="requires"):
        compile_template("@includeWhen(True)")
    with pytest.raises(SyntaxError, match="@each requires"):
        compile_template("@each('row', items)")


def test_split_args_escape_in_string(tmp_path: Path) -> None:
    views = tmp_path / "views"
    views.mkdir()
    (views / "bit.prism.html").write_text("ok", encoding="utf-8")
    (views / "page.prism.html").write_text(
        r"""@include('bit', {'x': 'a\'b'})""",
        encoding="utf-8",
    )
    assert Engine(paths=[views]).render("page") == "ok"


def test_xtags_duplicate_and_equals_inside_value() -> None:
    assert _parse_attrs('class="x" class ') == {"class": "x"}
    attrs = _parse_attrs('title="weird=1" weird')
    assert attrs.get("title") == "weird=1"
    out = expand_x_tags('<x-icon class="x" class />')
    assert "@component('icon'" in out


def test_engine_find_extension_cache_and_leftovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    views = tmp_path / "views"
    views.mkdir()
    (views / "hi.prism.html").write_text("H", encoding="utf-8")
    engine = Engine(paths=[views, tmp_path / "missing-dir"])
    (views / "ghost.prism.html").mkdir()
    assert engine.find("hi.prism.html").name == "hi.prism.html"
    assert engine.find("hi").name == "hi.prism.html"
    assert engine.cache_views() >= 1

    # Composer whose pattern does not match still exercises the miss branch.
    engine.composer("never-match", lambda ctx: ctx.update(z=1))

    pkg = tmp_path / "app" / "view" / "components"
    pkg.mkdir(parents=True)
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "view" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "badge.py").write_text(
        """
from almasix.prism import Component
class Badge(Component):
    def __init__(self, label: str = ""):
        self.label = label
    def render(self):
        return "components.badge"
""".strip(),
        encoding="utf-8",
    )
    (pkg / "plain.py").write_text(
        "class Plain:\n    pass\n",
        encoding="utf-8",
    )
    (views / "components").mkdir(exist_ok=True)
    (views / "components" / "badge.prism.html").write_text(
        "<b>{{ label }}{{ attributes }}</b>",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    import sys

    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            sys.modules.pop(mod, None)
    try:
        assert engine.resolve_component_class("plain") is None
        assert engine.resolve_component_class("missing.nope") is None
        html = engine.render_component(
            "badge",
            {},
            slot="",
            slots={},
            attrs={"label": "L", "class": "c"},
        )
        assert "L" in html
        assert "c" in html
        assert engine.render("hi") == "H"
    finally:
        for mod in list(sys.modules):
            if mod == "app" or mod.startswith("app."):
                sys.modules.pop(mod, None)


def test_instantiate_signature_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    class Odd(Component):
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def render(self) -> str:
            return "components.odd"

    def boom(_fn):
        raise TypeError("no signature")

    monkeypatch.setattr(inspect, "signature", boom)
    inst = Engine._instantiate_component(Odd, {"a": 1})
    assert inst.kwargs == {"a": 1}
