"""Prism control-flow directive tests."""

from __future__ import annotations

from almasix.prism.compiler import compile_template


def test_if_else() -> None:
    render = compile_template("@if(ok)yes@else\nno@endif")
    assert "yes" in render({"ok": True}, None)
    assert "no" in render({"ok": False}, None)


def test_unless() -> None:
    render = compile_template("@unless(ok)hidden@endunless")
    assert "hidden" in render({"ok": False}, None)
    assert "hidden" not in render({"ok": True}, None)


def test_foreach_loop() -> None:
    render = compile_template("@foreach(items as item)[{{ item }}]@endforeach")
    assert render({"items": ["a", "b"]}, None) == "[a][b]"


def test_foreach_loop_variable() -> None:
    render = compile_template("@foreach(items as item)@if(loop.first)F@endif{{ item }}@endforeach")
    assert render({"items": ["x", "y"]}, None) == "Fxy"


def test_forelse_empty() -> None:
    render = compile_template("@forelse(items as item){{ item }}@empty\nnone@endforelse")
    assert "none" in render({"items": []}, None)
    assert "a" in render({"items": ["a"]}, None)


def test_python_block() -> None:
    render = compile_template("@python\nn = n + 1\n@endpython{{ n }}")
    assert render({"n": 1}, None) == "2"


def test_for_python_style() -> None:
    render = compile_template("@for(i in range(3)){{ i }}@endfor")
    assert render({}, None) == "012"


def test_for_c_style_blade_parity() -> None:
    """Blade-shaped ``@for(i = 0; i < n; i++)`` compiles to a while + increment."""
    render = compile_template("@for(i = 0; i < 3; i++)\n<li>Notification {{ i + 1 }}</li>\n@endfor")
    out = render({}, None)
    assert "Notification 1" in out
    assert "Notification 2" in out
    assert "Notification 3" in out
    assert "Notification 4" not in out


def test_for_c_style_decrement_and_nested() -> None:
    render = compile_template(
        "@for(i = 2; i >= 0; i--)@for(j = 0; j < 2; j++){{ i }}{{ j }};@endfor@endfor"
    )
    assert render({}, None) == "20;21;10;11;00;01;"
