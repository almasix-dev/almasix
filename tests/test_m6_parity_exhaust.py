"""Exhaust remaining M6 Prism Blade-parity surfaces."""

from __future__ import annotations

from pathlib import Path

import pytest

from almasix.prism.compiler import compile_template
from almasix.prism.engine import Engine


def test_include_with_data_dict(tmp_path: Path) -> None:
    views = tmp_path / "views"
    views.mkdir()
    (views / "partial.prism.html").write_text("<em>{{ label }}</em>", encoding="utf-8")
    (views / "page.prism.html").write_text(
        "@include('partial', {'label': 'from-data'})",
        encoding="utf-8",
    )
    engine = Engine(paths=[views])
    assert engine.render("page") == "<em>from-data</em>"


def test_include_if_missing_vs_present(tmp_path: Path) -> None:
    views = tmp_path / "views"
    views.mkdir()
    (views / "ok.prism.html").write_text("OK", encoding="utf-8")
    (views / "page.prism.html").write_text(
        "A@includeIf('missing')B@includeIf('ok')C",
        encoding="utf-8",
    )
    engine = Engine(paths=[views])
    assert engine.render("page") == "ABOKC"
    assert engine.exists("ok") is True
    assert engine.exists("missing") is False


def test_include_when_and_unless(tmp_path: Path) -> None:
    views = tmp_path / "views"
    views.mkdir()
    (views / "bit.prism.html").write_text("X", encoding="utf-8")
    (views / "page.prism.html").write_text(
        "@includeWhen(show, 'bit')|@includeUnless(show, 'bit')",
        encoding="utf-8",
    )
    engine = Engine(paths=[views])
    assert engine.render("page", {"show": True}) == "X|"
    assert engine.render("page", {"show": False}) == "|X"


def test_each_with_items_and_empty_view(tmp_path: Path) -> None:
    views = tmp_path / "views"
    views.mkdir()
    (views / "row.prism.html").write_text("[{{ item }}]", encoding="utf-8")
    (views / "none.prism.html").write_text("empty", encoding="utf-8")
    (views / "page.prism.html").write_text(
        "@each('row', items, 'item', 'none')",
        encoding="utf-8",
    )
    engine = Engine(paths=[views])
    assert engine.render("page", {"items": ["a", "b"]}) == "[a][b]"
    assert engine.render("page", {"items": []}) == "empty"


def test_isset_endisset() -> None:
    render = compile_template("@isset(name)hi@endisset")
    assert render({"name": "x"}, None) == "hi"
    assert render({"name": None}, None) == ""


def test_empty_expr_and_forelse_empty() -> None:
    empty_var = compile_template("@empty(items)none@endempty")
    assert empty_var({"items": []}, None) == "none"
    assert empty_var({"items": [1]}, None) == ""

    forelse = compile_template("@forelse(items as item){{ item }}@empty\nnone@endforelse")
    assert "none" in forelse({"items": []}, None)
    assert "a" in forelse({"items": ["a"]}, None)


def test_csrf_stub() -> None:
    render = compile_template("@csrf")
    html = render({"csrf_token": "tok"}, None)
    assert 'name="_token"' in html
    assert 'value="tok"' in html
    assert 'type="hidden"' in html


def test_dump_and_dd_directives() -> None:
    from almasix.debug import DumpAndDie

    dump_render = compile_template("before @dump(user) after", name="demo.dump")
    html = dump_render({"user": {"name": "Ada"}}, None)
    assert "before" in html and "after" in html
    assert "almasix-dump" in html
    assert "Ada" in html or "&quot;Ada&quot;" in html
    assert "demo.dump" in html

    multi = compile_template("@dump(a, b)")
    multi_html = multi({"a": 1, "b": True}, None)
    assert "#0" in multi_html and "#1" in multi_html

    bare = compile_template("@dump")
    assert "almasix-dump" in bare({}, None)

    dd_render = compile_template("@dd(user)")
    with pytest.raises(DumpAndDie) as caught:
        dd_render({"user": {"id": 7}}, None)
    assert caught.value.values == ({"id": 7},)


def test_error_enderror() -> None:
    render = compile_template("@error('email'){{ message }}@enderror")
    assert render({"errors": {"email": ["bad"]}}, None) == "bad"
    assert render({"errors": {}}, None) == ""
    assert render({}, None) == ""


def test_auth_guest_stubs() -> None:
    auth = compile_template("@auth\nIN@endauth")
    guest = compile_template("@guest\nOUT@endguest")
    assert "IN" in auth({"auth_user": {"id": 1}}, None)
    assert "IN" not in auth({}, None)
    assert "OUT" in guest({}, None)
    assert "OUT" not in guest({"__authenticated": True}, None)


def test_asset_directive() -> None:
    render = compile_template("@asset('css/app.css')")
    html = render({"asset": lambda path, absolute=True: f"/static/{path}"}, None)
    assert html == "/static/css/app.css"


def test_custom_engine_directive(tmp_path: Path) -> None:
    views = tmp_path / "views"
    views.mkdir()
    (views / "page.prism.html").write_text("@datetime('now')", encoding="utf-8")
    engine = Engine(paths=[views])
    engine.directive("datetime", lambda expr: f"__w({expr})")
    assert engine.render("page") == "now"


def test_composer_and_creator(tmp_path: Path) -> None:
    views = tmp_path / "views"
    (views / "profile").mkdir(parents=True)
    (views / "profile" / "show.prism.html").write_text("{{ title }}", encoding="utf-8")
    engine = Engine(paths=[views])
    created: list[str] = []

    def create(ctx: dict) -> None:
        created.append("once")
        ctx["seed"] = "created"

    def compose(ctx: dict) -> None:
        ctx["title"] = ctx.get("seed", "compose") + "+"

    engine.creator("profile.*", create)
    engine.composer("profile.*", compose)
    assert engine.render("profile.show") == "created+"
    assert engine.render("profile.show") == "compose+"
    assert created == ["once"]


def test_fragment_cache(tmp_path: Path) -> None:
    views = tmp_path / "views"
    views.mkdir()
    (views / "page.prism.html").write_text(
        "@cache('frag'){{ n }}@endcache",
        encoding="utf-8",
    )
    engine = Engine(paths=[views])
    assert engine.render("page", {"n": 1}) == "1"
    assert engine.render("page", {"n": 2}) == "1"
    engine.clear_cache()
    assert engine.render("page", {"n": 3}) == "3"


def test_cache_views_and_clear_cache(tmp_path: Path) -> None:
    views = tmp_path / "views"
    (views / "mail").mkdir(parents=True)
    (views / "a.prism.html").write_text("A", encoding="utf-8")
    (views / "mail" / "b.prism.html").write_text("B", encoding="utf-8")
    engine = Engine(paths=[views])
    assert engine.cache_views() == 2
    assert len(engine._cache) == 2
    engine.remember_fragment("k", lambda: "x")
    engine._created.add("a")
    engine.clear_cache()
    assert engine._cache == {}
    assert engine._fragments == {}
    assert engine._created == set()
    assert engine.warm_cache() == 2
