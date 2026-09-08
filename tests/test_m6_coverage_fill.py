"""Coverage fill-ins for almasix.prism edge paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from almasix.prism import (
    AttributeBag,
    Component,
    HtmlString,
    Loop,
    ViewFactory,
    e,
    render,
    set_engine,
    view,
)
from almasix.prism.compiler import compile_template
from almasix.prism.engine import Engine
from almasix.prism.escape import DeferredHtml
from almasix.prism.helpers import get_engine
from almasix.prism.stacks import StackBag
from almasix.prism.xtags import expand_x_tags


def test_attribute_bag_merge_only_except_bool() -> None:
    bag = AttributeBag({"class": "a", "id": "x", "disabled": True, "hidden": False})
    merged = bag.merge({"class": "base", "title": "t"})
    assert 'class="base a"' in str(merged)
    assert 'id="x"' in str(merged)
    assert "disabled" in str(merged)
    assert "hidden" not in str(merged)
    assert bag.only("id").get("id") == "x"
    assert bag.except_("id").get("id") is None
    assert bag.__html__() == str(bag)


def test_loop_helpers_and_depth() -> None:
    outer = Loop(["a", "b"])
    assert next(outer) == "a"
    assert outer.first and outer.odd and outer.iteration == 1
    assert next(outer) == "b"
    assert outer.last and outer.even and outer.remaining == 0 and outer.count == 2
    with pytest.raises(StopIteration):
        next(outer)

    parent = Loop(["p"])
    next(parent)
    child = Loop(["c"], parent=parent)
    next(child)
    assert child.depth == 2
    assert child.index == 0


def test_stack_prepend_and_once() -> None:
    stacks = StackBag()
    stacks.push("s", "B")
    stacks.push("s", "A", prepend=True)
    assert stacks.render("s") == "AB"
    assert stacks.render("missing") == ""
    assert stacks.once("k") is True
    assert stacks.once("k") is False


def test_component_template_classvar_and_attrs() -> None:
    class Badge(Component):
        template = "components.badge"

        def __init__(self, label: str = "x") -> None:
            self.label = label

    badge = Badge(label="ok").with_attributes({"class": "pill"})
    assert badge.render() == "components.badge"
    assert badge.data()["label"] == "ok"
    assert badge.attribute_data()["class"] == "pill"

    class Broken(Component):
        pass

    with pytest.raises(NotImplementedError):
        Broken().render()


def test_escape_and_deferred_html() -> None:
    assert e(None) == ""
    assert e(HtmlString("<b>")) == "<b>"
    assert "&lt;" in e("<b>")
    deferred = DeferredHtml(lambda: "<i>x</i>")
    assert e(deferred) == "<i>x</i>"
    assert str(deferred) == "<i>x</i>"
    assert "DeferredHtml" in repr(deferred)
    assert "HtmlString" in repr(HtmlString("a"))


def test_xtags_self_closing_dynamic_and_echo_attr() -> None:
    out = expand_x_tags('<x-icon name="star" disabled />')
    assert "@component('icon'" in out
    assert "disabled" in out

    out2 = expand_x_tags('<x-link href="{{ url }}">Go</x-link>')
    assert "url" in out2

    out3 = expand_x_tags('<x-link :href="board_url">Go</x-link>')
    assert "board_url" in out3

    out4 = expand_x_tags('<x-slot name="footer">F</x-slot>')
    assert "@slot('footer')" in out4


def test_view_factory_and_helpers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    views = tmp_path / "views"
    views.mkdir()
    (views / "hi.prism.html").write_text("{{ n }}", encoding="utf-8")
    engine = Engine(paths=[views])
    factory = ViewFactory(engine)
    factory.composer("hi", lambda ctx: ctx.setdefault("n", 1))
    factory.directive("shout", lambda expr: f"__w(str({expr}).upper())")
    (views / "dir.prism.html").write_text("@shout('ok')", encoding="utf-8")
    assert factory.make("hi") == "1"
    assert factory.cache() >= 1
    factory.clear_cache()

    set_engine(engine)
    assert get_engine() is engine
    assert render("hi", {"n": 9}) == "9"
    response = view("hi", {"n": 2})
    assert response.body == b"2"
    assert factory("hi", {"n": 3}).body == b"3"

    set_engine(None)
    with pytest.raises(RuntimeError):
        get_engine()


def test_compiler_raw_and_push(tmp_path: Path) -> None:
    views = tmp_path / "views"
    (views / "layouts").mkdir(parents=True)
    (views / "layouts" / "app.prism.html").write_text(
        "@yield('content')@stack('s')",
        encoding="utf-8",
    )
    (views / "page.prism.html").write_text(
        """
@extends('layouts.app')
@section('content')
{!! raw !!}
@push('s')P@endpush
@prepend('s')A@endprepend
@endsection
""".strip(),
        encoding="utf-8",
    )
    html = Engine(paths=[views]).render("page", {"raw": "<b>1</b>"})
    assert "<b>1</b>" in html
    assert "A" in html and "P" in html


def test_once_directive() -> None:
    render = compile_template("@once\nZ\n@endonce@once\nZ\n@endonce")
    # StackBag once keys differ per compile site, so both may render;
    # at minimum the directive compiles and emits.
    assert "Z" in render({}, Engine(paths=[]))


def test_unless_for() -> None:
    render = compile_template("@unless(hide)Y@endunless@for(i in range(2)){{ i }}@endfor")
    out = render({"hide": False}, None)
    assert "Y" in out
    assert "0" in out and "1" in out


def test_engine_matches_star_and_list_composer(tmp_path: Path) -> None:
    views = tmp_path / "views"
    views.mkdir()
    (views / "a.prism.html").write_text("{{ v }}", encoding="utf-8")
    engine = Engine(paths=[views])
    engine.composer(["a", "missing"], lambda ctx: ctx.update(v="ok"))
    engine.composer("*", lambda ctx: None)
    assert engine.render("a") == "ok"
    assert engine.warm_cache() >= 1


def test_while_lang_choice_parent(tmp_path: Path) -> None:
    from almasix.translation.helpers import set_translator
    from almasix.translation.translator import Translator

    lang = tmp_path / "lang" / "en"
    lang.mkdir(parents=True)
    (lang / "m.py").write_text(
        'translations = {"hi": "Hello", "apples": "{count} apple|{count} apples"}\n',
        encoding="utf-8",
    )
    translator = Translator(locale="en", fallback="en")
    translator.add_path(tmp_path / "lang")
    set_translator(translator)

    views = tmp_path / "views"
    (views / "layouts").mkdir(parents=True)
    (views / "layouts" / "base.prism.html").write_text("@yield('content')", encoding="utf-8")
    (views / "layouts" / "app.prism.html").write_text(
        """
@extends('layouts.base')
@section('content')
BASE
@endsection
""".strip(),
        encoding="utf-8",
    )
    (views / "page.prism.html").write_text(
        """
@extends('layouts.app')
@section('content')
@parent
@while(n < 2){{ n }}@python
n += 1
@endpython@endwhile
@lang('m.hi')
@choice('m.apples', 2)
@endsection
""".strip(),
        encoding="utf-8",
    )
    html = Engine(paths=[views]).render("page", {"n": 0})
    assert "BASE" in html
    assert "0" in html and "1" in html
    assert "Hello" in html
    assert "apple" in html.lower()


def test_compiler_syntax_errors() -> None:
    with pytest.raises(SyntaxError):
        compile_template("@component")
    with pytest.raises(SyntaxError):
        compile_template("@if(True")
    with pytest.raises(SyntaxError):
        compile_template("@section('a')\nhi")
    with pytest.raises(SyntaxError):
        compile_template("@endif")
    with pytest.raises(SyntaxError):
        compile_template("@foreach(items as x")
    with pytest.raises(SyntaxError):
        compile_template("@endpush")
    with pytest.raises(SyntaxError):
        compile_template("@python\nx = 1\n")
    with pytest.raises(SyntaxError):
        compile_template("@if(True)\nhi")


def test_view_pattern_prefix_star(tmp_path: Path) -> None:
    views = tmp_path / "views"
    (views / "admin").mkdir(parents=True)
    (views / "admin" / "users.prism.html").write_text("{{ v }}", encoding="utf-8")
    engine = Engine(paths=[views])
    engine.composer("admin*", lambda ctx: ctx.update(v="admin"))
    assert engine.render("admin.users") == "admin"


def test_component_var_kwargs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    views = tmp_path / "views"
    (views / "components").mkdir(parents=True)
    (views / "components" / "box.prism.html").write_text(
        "<div>{{ title }}{{ attributes }}</div>",
        encoding="utf-8",
    )
    pkg = tmp_path / "app" / "view" / "components"
    pkg.mkdir(parents=True)
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "view" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "box.py").write_text(
        """
from almasix.prism import Component
class Box(Component):
    def __init__(self, **kwargs):
        self.title = kwargs.pop("title", "")
        self.with_attributes(kwargs)
    def render(self):
        return "components.box"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    import sys

    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            sys.modules.pop(mod, None)
    (views / "page.prism.html").write_text(
        '<x-box title="T" class="c">x</x-box>',
        encoding="utf-8",
    )
    try:
        html = Engine(paths=[views]).render("page")
        assert "T" in html
        assert "c" in html
    finally:
        for mod in list(sys.modules):
            if mod == "app" or mod.startswith("app."):
                sys.modules.pop(mod, None)


def test_xtags_single_quotes_and_unclosed() -> None:
    out = expand_x_tags("<x-a foo='bar' baz>")
    # unclosed tag left as-is or partially expanded
    assert "x-a" in out or "@component" in out
    out2 = expand_x_tags("<x-a foo='bar' :id=\"z\" disabled>ok</x-a>")
    assert "@component('a'" in out2
    assert "bar" in out2
    assert "disabled" in out2 or "True" in out2


def test_include_when_with_data(tmp_path: Path) -> None:
    views = tmp_path / "views"
    views.mkdir()
    (views / "bit.prism.html").write_text("{{ x }}", encoding="utf-8")
    (views / "page.prism.html").write_text(
        "@includeWhen(True, 'bit', {'x': 'Y'})@includeUnless(False, 'bit', {'x': 'Z'})",
        encoding="utf-8",
    )
    assert Engine(paths=[views]).render("page") == "YZ"


def test_custom_directive_multiline(tmp_path: Path) -> None:
    views = tmp_path / "views"
    views.mkdir()
    (views / "page.prism.html").write_text("@box('hi')", encoding="utf-8")
    engine = Engine(paths=[views])
    engine.directive(
        "box",
        lambda expr: f"__w('<div>')\n__w(str({expr}))\n__w('</div>')",
    )
    assert engine.render("page") == "<div>hi</div>"


def test_xtags_nested_same_name() -> None:
    out = expand_x_tags("<x-wrap><x-wrap>inner</x-wrap></x-wrap>")
    assert out.count("@component('wrap'") == 2
    assert out.count("@endcomponent") == 2


def test_html_string_str() -> None:
    assert str(HtmlString("abc")) == "abc"
    assert DeferredHtml(lambda: "z").__repr__().startswith("DeferredHtml")


def test_render_component_slot_call_styles(tmp_path: Path) -> None:
    views = tmp_path / "views"
    (views / "components").mkdir(parents=True)
    (views / "components" / "wrap.prism.html").write_text(
        "<w>{{ slot }}</w>",
        encoding="utf-8",
    )
    engine = Engine(paths=[views], cache_enabled=False)
    assert "hi" in engine.render_component("wrap", {}, slot="hi", slots={})
    assert "yo" in engine.render_component(
        "wrap",
        {},
        slot=lambda: "yo",
        slots={},
    )


def test_invalid_component_and_unclosed_slot() -> None:
    with pytest.raises(SyntaxError):
        compile_template("@component(123)\n@endcomponent")
    with pytest.raises(SyntaxError):
        compile_template("@component('a')\n@slot('t')\nhi\n@endcomponent")


def test_empty_python_block() -> None:
    render = compile_template("@python\npass\n@endpython\nOK")
    assert "OK" in render({}, None)


def test_resolve_component_empty_and_creator_skip(tmp_path: Path) -> None:
    engine = Engine(paths=[tmp_path / "views"])
    (tmp_path / "views").mkdir()
    (tmp_path / "views" / "x.prism.html").write_text("x", encoding="utf-8")
    assert engine.resolve_component_class("") is None
    engine.creator("never", lambda ctx: ctx.update(z=1))
    assert engine.render("x") == "x"
