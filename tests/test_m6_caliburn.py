"""Prism MVP compiler and engine tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from almasix.prism.compiler import compile_template
from almasix.prism.engine import Engine, ViewNotFoundError
from almasix.prism.escape import e


def test_escape_quotes_and_none() -> None:
    assert e(None) == ""
    assert "&lt;b&gt;" in e("<b>")
    assert e('"x"') == "&quot;x&quot;"


def test_echo_escapes_html() -> None:
    render = compile_template("<p>{{ name }}</p>")
    out = render({"name": "<script>"}, engine=None)
    assert out == "<p>&lt;script&gt;</p>"


def test_raw_echo() -> None:
    render = compile_template("<p>{!! name !!}</p>")
    out = render({"name": "<b>x</b>"}, engine=None)
    assert out == "<p><b>x</b></p>"


def test_comments_stripped() -> None:
    render = compile_template("A{{-- hide --}}B")
    assert render({}, engine=None) == "AB"


def test_extends_section_yield(tmp_path: Path) -> None:
    views = tmp_path / "views"
    (views / "layouts").mkdir(parents=True)
    (views / "layouts" / "app.prism.html").write_text(
        "<html><title>@yield('title', 'App')</title><body>@yield('content')</body></html>",
        encoding="utf-8",
    )
    (views / "welcome.prism.html").write_text(
        """
@extends('layouts.app')
@section('title', 'Hi')
@section('content')
<h1>{{ name }}</h1>
@endsection
""".strip(),
        encoding="utf-8",
    )
    engine = Engine(paths=[views])
    html = engine.render("welcome", {"name": "Almasix"})
    assert "<title>Hi</title>" in html
    assert "<h1>Almasix</h1>" in html
    assert "@yield" not in html
    assert "@section" not in html


def test_include(tmp_path: Path) -> None:
    views = tmp_path / "views"
    views.mkdir()
    (views / "partial.prism.html").write_text("<em>{{ label }}</em>", encoding="utf-8")
    (views / "page.prism.html").write_text(
        "<div>@include('partial')</div>",
        encoding="utf-8",
    )
    engine = Engine(paths=[views])
    assert engine.render("page", {"label": "ok"}) == "<div><em>ok</em></div>"


def test_view_not_found(tmp_path: Path) -> None:
    engine = Engine(paths=[tmp_path])
    with pytest.raises(ViewNotFoundError):
        engine.render("missing")


def test_cache_invalidates_on_mtime(tmp_path: Path) -> None:
    views = tmp_path / "views"
    views.mkdir()
    path = views / "x.prism.html"
    path.write_text("one", encoding="utf-8")
    engine = Engine(paths=[views])
    assert engine.render("x") == "one"
    path.write_text("two", encoding="utf-8")
    # Ensure mtime changes on fast filesystems
    import os
    import time

    os.utime(path, (time.time() + 2, time.time() + 2))
    assert engine.render("x") == "two"


def test_dotted_view_name(tmp_path: Path) -> None:
    views = tmp_path / "views"
    (views / "mail").mkdir(parents=True)
    (views / "mail" / "hello.prism.html").write_text("hi", encoding="utf-8")
    engine = Engine(paths=[views])
    assert engine.render("mail.hello") == "hi"
