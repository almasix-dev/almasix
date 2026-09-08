"""Prism component + slot exhaust tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from almasix.prism.engine import Engine
from almasix.prism.xtags import expand_x_tags


def test_component_directive(tmp_path: Path) -> None:
    views = tmp_path / "views"
    (views / "components").mkdir(parents=True)
    (views / "components" / "alert.prism.html").write_text(
        '<div class="alert">{{ slot }}</div>',
        encoding="utf-8",
    )
    (views / "page.prism.html").write_text(
        "@component('alert')\nHello\n@endcomponent",
        encoding="utf-8",
    )
    engine = Engine(paths=[views])
    html = engine.render("page")
    assert '<div class="alert">' in html
    assert "Hello" in html


def test_named_slot(tmp_path: Path) -> None:
    views = tmp_path / "views"
    (views / "components").mkdir(parents=True)
    (views / "components" / "card.prism.html").write_text(
        "<h2>{{ title }}</h2><div>{{ slot }}</div>",
        encoding="utf-8",
    )
    (views / "page.prism.html").write_text(
        """
@component('card')
@slot('title')
Heading
@endslot
Body
@endcomponent
""".strip(),
        encoding="utf-8",
    )
    engine = Engine(paths=[views])
    html = engine.render("page")
    assert "Heading" in html
    assert "Body" in html
    assert "<h2>" in html


def test_multiple_named_slots(tmp_path: Path) -> None:
    views = tmp_path / "views"
    (views / "components").mkdir(parents=True)
    (views / "components" / "panel.prism.html").write_text(
        "<header>{{ header }}</header><main>{{ slot }}</main><footer>{{ footer }}</footer>",
        encoding="utf-8",
    )
    (views / "page.prism.html").write_text(
        """
@component('panel')
@slot('header')H@endslot
BODY
@slot('footer')F@endslot
@endcomponent
""".strip(),
        encoding="utf-8",
    )
    html = Engine(paths=[views]).render("page")
    assert "<header>" in html and "H" in html
    assert "<main>" in html and "BODY" in html
    assert "<footer>" in html and "F" in html


def test_x_tag_component(tmp_path: Path) -> None:
    views = tmp_path / "views"
    (views / "components").mkdir(parents=True)
    (views / "components" / "badge.prism.html").write_text(
        "<span {{ attributes }}>{{ slot }}</span>",
        encoding="utf-8",
    )
    (views / "page.prism.html").write_text(
        '<x-badge class="pill">OK</x-badge>',
        encoding="utf-8",
    )
    engine = Engine(paths=[views])
    html = engine.render("page")
    assert "OK" in html
    assert "pill" in html


def test_x_slot_syntax(tmp_path: Path) -> None:
    views = tmp_path / "views"
    (views / "components").mkdir(parents=True)
    (views / "components" / "card.prism.html").write_text(
        "<h2>{{ title }}</h2><p>{{ slot }}</p>",
        encoding="utf-8",
    )
    (views / "page.prism.html").write_text(
        """
<x-card>
  <x-slot:title>Hello</x-slot>
  Body copy
</x-card>
""".strip(),
        encoding="utf-8",
    )
    html = Engine(paths=[views]).render("page")
    assert "<h2>" in html and "Hello" in html
    assert "<p>" in html and "Body copy" in html


def test_x_slot_name_attribute(tmp_path: Path) -> None:
    views = tmp_path / "views"
    (views / "components").mkdir(parents=True)
    (views / "components" / "card.prism.html").write_text(
        "<h2>{{ title }}</h2>{{ slot }}",
        encoding="utf-8",
    )
    (views / "page.prism.html").write_text(
        """
<x-card>
  <x-slot name="title">T</x-slot>
  D
</x-card>
""".strip(),
        encoding="utf-8",
    )
    html = Engine(paths=[views]).render("page")
    assert "<h2>" in html and "T" in html
    assert "D" in html


def test_nested_x_components(tmp_path: Path) -> None:
    views = tmp_path / "views"
    (views / "components").mkdir(parents=True)
    (views / "components" / "card.prism.html").write_text(
        '<div class="card">{{ slot }}</div>',
        encoding="utf-8",
    )
    (views / "components" / "badge.prism.html").write_text(
        "<span>{{ slot }}</span>",
        encoding="utf-8",
    )
    (views / "page.prism.html").write_text(
        "<x-card>Hi <x-badge>new</x-badge></x-card>",
        encoding="utf-8",
    )
    html = Engine(paths=[views]).render("page")
    assert "card" in html
    assert "new" in html
    assert "span" in html


def test_dynamic_x_attr_binding(tmp_path: Path) -> None:
    views = tmp_path / "views"
    (views / "components").mkdir(parents=True)
    (views / "components" / "link.prism.html").write_text(
        '@props({"href": "#"})\n<a href="{{ href }}">{{ slot }}</a>',
        encoding="utf-8",
    )
    (views / "page.prism.html").write_text(
        '<x-link :href="target">Go</x-link>',
        encoding="utf-8",
    )
    html = Engine(paths=[views]).render("page", {"target": "/progress"})
    assert 'href="/progress"' in html
    assert "Go" in html


def test_aware_inherits_parent_component_data(tmp_path: Path) -> None:
    views = tmp_path / "views"
    (views / "components").mkdir(parents=True)
    (views / "components" / "form.prism.html").write_text(
        """
@props({"method": "post"})
<form method="{{ method }}">{{ slot }}</form>
""".strip(),
        encoding="utf-8",
    )
    (views / "components" / "input.prism.html").write_text(
        """
@aware(["method"])
@props({"name": "field"})
<input name="{{ name }}" data-method="{{ method }}">
""".strip(),
        encoding="utf-8",
    )
    (views / "page.prism.html").write_text(
        """
@component('form', {"method": "put"})
@component('input', {"name": "email"})
@endcomponent
@endcomponent
""".strip(),
        encoding="utf-8",
    )
    html = Engine(paths=[views]).render("page")
    assert 'method="put"' in html
    assert 'data-method="put"' in html
    assert 'name="email"' in html


def test_aware_explicit_child_attr_wins(tmp_path: Path) -> None:
    views = tmp_path / "views"
    (views / "components").mkdir(parents=True)
    (views / "components" / "form.prism.html").write_text(
        '@props({"method": "post"})\n<form>{{ slot }}</form>',
        encoding="utf-8",
    )
    (views / "components" / "input.prism.html").write_text(
        '@aware(["method"])\n@props({"method": "get"})\n<span>{{ method }}</span>',
        encoding="utf-8",
    )
    (views / "page.prism.html").write_text(
        """
@component('form', {"method": "put"})
@component('input', {"method": "patch"})
@endcomponent
@endcomponent
""".strip(),
        encoding="utf-8",
    )
    html = Engine(paths=[views]).render("page")
    assert "<span>patch</span>" in html


def test_class_based_component(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    views = tmp_path / "views"
    (views / "components").mkdir(parents=True)
    (views / "components" / "alert.prism.html").write_text(
        '<div class="alert-{{ type }}">{{ slot }}</div>',
        encoding="utf-8",
    )

    pkg = tmp_path / "app" / "view" / "components"
    pkg.mkdir(parents=True)
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "view" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "alert.py").write_text(
        """
from almasix.prism import Component

class Alert(Component):
    def __init__(self, type: str = "info") -> None:
        self.type = type

    def render(self) -> str:
        return "components.alert"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            sys.modules.pop(mod, None)

    (views / "page.prism.html").write_text(
        '<x-alert type="success">Saved</x-alert>',
        encoding="utf-8",
    )
    try:
        html = Engine(paths=[views]).render("page")
        assert 'class="alert-success"' in html
        assert "Saved" in html
    finally:
        for mod in list(sys.modules):
            if mod == "app" or mod.startswith("app."):
                sys.modules.pop(mod, None)


def test_component_attrs_allow_parens_in_strings(tmp_path: Path) -> None:
    views = tmp_path / "views"
    (views / "components").mkdir(parents=True)
    (views / "components" / "label.prism.html").write_text(
        '@props({"text": ""})\n<span>{{ text }}</span>',
        encoding="utf-8",
    )
    (views / "page.prism.html").write_text(
        "@component('label', {'text': 'Hello (world)'})\n@endcomponent",
        encoding="utf-8",
    )
    html = Engine(paths=[views]).render("page")
    assert "Hello (world)" in html


def test_expand_x_slot_to_directives() -> None:
    out = expand_x_tags('<x-card><x-slot:title>T</x-slot>Body</x-card>')
    assert "@component('card'" in out
    assert "@slot('title')" in out
    assert "@endslot" in out
