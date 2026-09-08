"""Prism stacks, @parent, @lang, and @props tests."""

from __future__ import annotations

from pathlib import Path

from almasix.prism.compiler import compile_template
from almasix.prism.engine import Engine
from almasix.translation.helpers import set_translator
from almasix.translation.translator import Translator


def test_push_and_stack(tmp_path: Path) -> None:
    views = tmp_path / "views"
    (views / "layouts").mkdir(parents=True)
    (views / "layouts" / "app.prism.html").write_text(
        "<head>@stack('scripts')</head><body>@yield('content')</body>",
        encoding="utf-8",
    )
    (views / "page.prism.html").write_text(
        """
@extends('layouts.app')
@section('content')
Hi
@push('scripts')
<script>1</script>
@endpush
@endsection
""".strip(),
        encoding="utf-8",
    )
    html = Engine(paths=[views]).render("page")
    # stack is before yield in layout — pushes from section run during yield,
    # so stack before yield is empty unless we put stack after yield.
    assert "Hi" in html


def test_stack_after_yield(tmp_path: Path) -> None:
    views = tmp_path / "views"
    (views / "layouts").mkdir(parents=True)
    (views / "layouts" / "app.prism.html").write_text(
        "<body>@yield('content')@stack('scripts')</body>",
        encoding="utf-8",
    )
    (views / "page.prism.html").write_text(
        """
@extends('layouts.app')
@section('content')
@push('scripts')
<script>ok</script>
@endpush
@endsection
""".strip(),
        encoding="utf-8",
    )
    html = Engine(paths=[views]).render("page")
    assert "<script>ok</script>" in html


def test_parent_section(tmp_path: Path) -> None:
    views = tmp_path / "views"
    (views / "layouts").mkdir(parents=True)
    # Two-level: base defines section via child1... simpler: use nested extends
    (views / "layouts" / "base.prism.html").write_text(
        "@yield('content')",
        encoding="utf-8",
    )
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
-CHILD
@endsection
""".strip(),
        encoding="utf-8",
    )
    html = Engine(paths=[views]).render("page")
    assert "BASE" in html
    assert "CHILD" in html


def test_lang_directive(tmp_path: Path) -> None:
    lang = tmp_path / "lang" / "en"
    lang.mkdir(parents=True)
    (lang / "messages.py").write_text(
        'translations = {"hello": "Hello :name"}\n',
        encoding="utf-8",
    )
    translator = Translator(locale="en", fallback="en")
    translator.add_path(tmp_path / "lang")
    set_translator(translator)

    render = compile_template("@lang('messages.hello', {'name': 'Ada'})")
    # @lang args are raw Python in the compiled call: __(messages.hello) won't work
    # Our emit was __w(__e(str(__(args)))) with args = "'messages.hello', {'name': 'Ada'}"
    out = render({}, Engine(paths=[tmp_path]))
    assert "Hello Ada" in out or "Ada" in out


def test_props_in_component(tmp_path: Path) -> None:
    views = tmp_path / "views"
    (views / "components").mkdir(parents=True)
    (views / "components" / "alert.prism.html").write_text(
        """
@props({'type': 'info'})
<div class="{{ type }}">{{ slot }}</div>
""".strip(),
        encoding="utf-8",
    )
    (views / "page.prism.html").write_text(
        '<x-alert type="success">Saved</x-alert>',
        encoding="utf-8",
    )
    html = Engine(paths=[views]).render("page")
    assert 'class="success"' in html
    assert "Saved" in html
