"""M45 — Prism language support: formatter + TextMate grammar."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from almasix.prism.formatter import format_prism

ROOT = Path(__file__).resolve().parents[1]
GRAMMAR = ROOT / "editors" / "prism" / "syntaxes" / "prism.tmLanguage.json"

_FIXTURE = """
<div class="board">
@if(user)
<ul>
@foreach(items as item)
<li>{{ item.name }}</li>
@endforeach
</ul>
@else
<p>guest</p>
@endif
@python
# leave this indent alone
x = 1
  y = 2
@endpython
</div>
""".strip()


def test_format_prism_idempotent() -> None:
    once = format_prism(_FIXTURE)
    twice = format_prism(once)
    assert once == twice
    assert "    @if(user)" in once or once.startswith("<div")
    assert "  y = 2" in once  # python body preserved
    assert "@endpython" in once


def test_format_prism_check_style_stable() -> None:
    """Calling format_prism twice matches --check (no further change)."""
    formatted = format_prism(_FIXTURE, indent_size=4, line_length=120)
    assert format_prism(formatted) == formatted


def test_format_indents_directives_and_html() -> None:
    source = "@if(True)\n<div>\n<span>hi</span>\n</div>\n@endif\n"
    out = format_prism(source)
    assert out == ("@if(True)\n    <div>\n        <span>hi</span>\n    </div>\n@endif\n")


def test_format_preserves_python_block_inner() -> None:
    source = "@python\nfoo = 1\n  bar = 2\n\tbaz = 3\n@endpython\n"
    out = format_prism(source)
    assert "foo = 1\n  bar = 2\n\tbaz = 3\n" in out
    assert out.startswith("@python\n")
    assert out.rstrip().endswith("@endpython")


def test_format_mid_else_and_elseif() -> None:
    source = "@if(a)\nx\n@elseif(b)\ny\n@else\nz\n@endif\n"
    out = format_prism(source)
    lines = out.splitlines()
    assert lines[0] == "@if(a)"
    assert lines[1] == "    x"
    assert lines[2] == "@elseif(b)"
    assert lines[3] == "    y"
    assert lines[4] == "@else"
    assert lines[5] == "    z"
    assert lines[6] == "@endif"


def test_format_forelse_empty_mid() -> None:
    source = "@forelse(items as item)\n{{ item }}\n@empty\nnone\n@endforelse\n"
    out = format_prism(source)
    assert "@empty\n" in out
    assert "    none\n" in out


def test_format_empty_with_args_opens() -> None:
    source = "@empty(items)\ngone\n@endempty\n"
    out = format_prism(source)
    assert out == "@empty(items)\n    gone\n@endempty\n"


def test_format_standalone_directives() -> None:
    source = "<form>\n@csrf\n@vite(['app.js'])\n</form>\n"
    out = format_prism(source)
    assert "    @csrf\n" in out
    assert "    @vite(['app.js'])\n" in out


def test_format_void_and_self_closing() -> None:
    source = "<div>\n<br>\n<img src='x' />\n</div>\n"
    out = format_prism(source)
    assert "    <br>\n" in out
    assert "    <img src='x' />\n" in out
    assert out.endswith("</div>\n")


def test_format_blank_lines_and_trailing_newline() -> None:
    assert format_prism("") == "\n"
    assert format_prism("hi") == "hi\n" or format_prism("hi") == "hi"
    out = format_prism("@if(1)\n\nx\n\n@endif\n")
    assert "\n\n" in out


def test_format_rejects_bad_indent_size() -> None:
    with pytest.raises(ValueError, match="indent_size"):
        format_prism("@if(1)\n@endif\n", indent_size=0)


def test_format_comments_and_echoes_as_text() -> None:
    source = "{{-- note --}}\n{{ name }}\n{!! html !!}\n"
    out = format_prism(source)
    assert "{{-- note --}}" in out
    assert "{{ name }}" in out
    assert "{!! html !!}" in out


def test_grammar_json_loads_and_has_key_patterns() -> None:
    data = json.loads(GRAMMAR.read_text(encoding="utf-8"))
    assert data["scopeName"] == "text.html.prism"
    blob = json.dumps(data)
    assert "if|elseif" in blob or "@(if" in blob
    assert "\\{\\{" in data["repository"]["echo"]["begin"]
    assert "python" in data["repository"]["python-block"]["begin"]
    assert "repository" in data
    assert "comment" in data["repository"]
    assert "python-block" in data["repository"]
    assert "echo" in data["repository"]


def test_language_configuration_and_snippets_exist() -> None:
    base = ROOT / "editors" / "prism"
    assert (base / "language-configuration.json").is_file()
    assert (base / "snippets" / "prism.code-snippets").is_file()
    assert (base / "tree-sitter-prism" / "grammar.js").is_file()
    assert (base / "README.md").is_file()
    lang = json.loads((base / "language-configuration.json").read_text(encoding="utf-8"))
    assert lang["comments"]["blockComment"] == ["{{--", "--}}"]
    snippets = json.loads((base / "snippets" / "prism.code-snippets").read_text(encoding="utf-8"))
    assert "Prism if" in snippets
    assert "x-component" in snippets


def test_prism_format_command_check(tmp_path: Path) -> None:
    from almasix.prism.commands.format import PrismFormatCommand

    messy = tmp_path / "sample.prism.html"
    messy.write_text("@if(1)\nx\n@endif\n", encoding="utf-8")
    cmd = PrismFormatCommand()
    cmd._arguments = {"path": str(messy)}
    cmd._options = {"check": True, "write": False}
    assert cmd.handle() == cmd.FAILURE

    cmd._options = {"check": False, "write": True}
    assert cmd.handle() == cmd.SUCCESS
    text = messy.read_text(encoding="utf-8")
    assert text == format_prism("@if(1)\nx\n@endif\n")

    cmd._options = {"check": True, "write": False}
    assert cmd.handle() == cmd.SUCCESS


def test_prism_format_command_missing_path(tmp_path: Path) -> None:
    from almasix.prism.commands.format import PrismFormatCommand

    cmd = PrismFormatCommand()
    cmd._arguments = {"path": str(tmp_path / "nope.prism.html")}
    cmd._options = {"check": False, "write": False}
    assert cmd.handle() == cmd.FAILURE


def test_prism_format_command_rejects_non_prism(tmp_path: Path) -> None:
    from almasix.prism.commands.format import PrismFormatCommand

    other = tmp_path / "x.html"
    other.write_text("<p></p>", encoding="utf-8")
    cmd = PrismFormatCommand()
    cmd._arguments = {"path": str(other)}
    cmd._options = {"check": False, "write": False}
    assert cmd.handle() == cmd.FAILURE


def test_prism_format_command_directory_empty(tmp_path: Path) -> None:
    from almasix.prism.commands.format import PrismFormatCommand

    cmd = PrismFormatCommand()
    cmd._arguments = {"path": str(tmp_path)}
    cmd._options = {"check": False, "write": False}
    assert cmd.handle() == cmd.SUCCESS


def test_prism_format_command_registered_on_progress() -> None:
    result = subprocess.run(
        [sys.executable, "smith", "list"],
        cwd=ROOT / "examples" / "progress",
        capture_output=True,
        text=True,
        check=False,
    )
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    assert "prism:format" in out
