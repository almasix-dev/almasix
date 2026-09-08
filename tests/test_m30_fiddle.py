"""M30 — the Fiddle allow-list (Tinker's ``commands`` / ``alias`` / ``dont_alias``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from avalon.console.kernel import ConsoleKernel
from avalon.console.repl import build_namespace
from avalon.installer.scaffold import scaffold_app

MODEL = '''
from avalon.orm import Model


class Widget(Model):
    fillable = ("name",)
'''

#: Fiddle reaches for ``User`` by name before it discovers anything, the way
#: Tinker does, so the refusal below has to be tested against a real one.
USER = '''
from avalon.orm import Model


class User(Model):
    fillable = ("email",)
'''


@pytest.fixture()
def app_root(tmp_path: Path) -> Path:
    root = scaffold_app("fiddleapp", destination=tmp_path / "fiddleapp")
    (root / "app" / "models" / "widget.py").write_text(MODEL, encoding="utf-8")
    (root / "app" / "models" / "user.py").write_text(USER, encoding="utf-8")
    return root


def configure(root: Path, body: str) -> None:
    (root / "config" / "fiddle.py").write_text(f"config = {body}\n", encoding="utf-8")


def test_a_new_application_is_scaffolded_with_the_fiddle_config(app_root: Path) -> None:
    config = (app_root / "config" / "fiddle.py").read_text(encoding="utf-8")

    for key in ("commands", "alias", "dont_alias"):
        assert f'"{key}"' in config


def test_models_arrive_in_the_shell_unless_they_are_refused(app_root: Path) -> None:
    kernel = ConsoleKernel.from_cwd(app_root)
    assert "Widget" in build_namespace(kernel.app)

    configure(app_root, '{"dont_alias": ["Widget", "User"]}')
    refused = ConsoleKernel.from_cwd(app_root)
    namespace = build_namespace(refused.app)

    assert "Widget" not in namespace
    assert "User" not in namespace


def test_alias_brings_in_anything_by_dotted_path(app_root: Path) -> None:
    configure(app_root, '{"alias": {"Str": "avalon.support.Str", "Nope": "avalon.no.Such"}}')

    namespace = build_namespace(ConsoleKernel.from_cwd(app_root).app)

    from avalon.support import Str

    assert namespace["Str"] is Str
    assert "Nope" not in namespace


def test_an_alias_the_dont_alias_list_refuses_stays_out(app_root: Path) -> None:
    configure(app_root, '{"alias": {"Str": "avalon.support.Str"}, "dont_alias": ["Str"]}')

    assert "Str" not in build_namespace(ConsoleKernel.from_cwd(app_root).app)


def test_commands_become_callables(app_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Tinker lists commands to type; a Python REPL gets functions to call."""
    configure(app_root, '{"commands": ["inspire", "no:such:command"]}')

    namespace = build_namespace(ConsoleKernel.from_cwd(app_root).app)

    assert "no such command" in capsys.readouterr().out
    assert callable(namespace["inspire"])
    assert namespace["inspire"].__doc__ == "Run the 'inspire' command."
    assert namespace["inspire"]() == 0
    assert capsys.readouterr().out.strip()


def test_a_command_callable_passes_arguments_and_options(app_root: Path) -> None:
    configure(app_root, '{"commands": ["make:controller"]}')

    namespace = build_namespace(ConsoleKernel.from_cwd(app_root).app)
    make_controller = namespace["make_controller"]

    import os

    cwd = os.getcwd()
    os.chdir(app_root)
    try:
        assert make_controller("WidgetController") == 0
        assert make_controller("WidgetController", force=True) == 0
    finally:
        os.chdir(cwd)

    assert (app_root / "app" / "http" / "controllers" / "widget_controller.py").is_file()
