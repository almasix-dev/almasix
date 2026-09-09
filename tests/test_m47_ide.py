"""Unit tests for ``almasix.ide`` (M47) — aim ≥98% coverage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from almasix.ide import generate_stubs, install_editor_config
from almasix.ide.install import (
    IdeInstallResult,
    _locate_grammar,
    _merge_settings,
    _write_jetbrains_note,
    _write_vscode,
)
from almasix.ide.stubs import (
    StubResult,
    _dict_casts,
    _guess_class_name,
    _pascal,
    _route_names,
    _tuple_strings,
    extract_model_columns,
    render_model_stub,
    render_routes_stub,
)


def test_render_model_stub_empty() -> None:
    text = render_model_stub("Empty", {})
    assert "class Empty(Model):" in text
    assert "id: Any" in text


def test_render_model_stub_columns() -> None:
    text = render_model_stub("Post", {"title": "str", "views": "int", "id": "Any"})
    assert "title: str" in text
    assert "views: int" in text


def test_render_routes_stub_variants() -> None:
    assert 'Literal[""]' in render_routes_stub([])
    assert 'Literal["home"]' in render_routes_stub(["home"])
    multi = render_routes_stub(["b", "a", "a"])
    assert "Literal[" in multi
    assert '"a",' in multi
    assert '"b",' in multi


def test_extract_and_guess(tmp_path: Path) -> None:
    model = tmp_path / "post.py"
    model.write_text(
        "class Other:\n    pass\n\n"
        "class Post:\n"
        '    fillable = ("title", "views")\n'
        '    casts = {"views": "int", "published": "bool"}\n',
        encoding="utf-8",
    )
    cols = extract_model_columns(model)
    assert cols["title"] == "Any"
    assert cols["views"] == "int"
    assert cols["published"] == "bool"
    assert _guess_class_name(model, "post") == "Post"
    assert _pascal("user_profile") == "UserProfile"


def test_guess_class_name_fallbacks(tmp_path: Path) -> None:
    bad = tmp_path / "weird.py"
    bad.write_text("not valid python (((", encoding="utf-8")
    assert _guess_class_name(bad, "weird") == "Weird"
    empty = tmp_path / "empty.py"
    empty.write_text("# no classes\n", encoding="utf-8")
    assert _guess_class_name(empty, "empty") == "Empty"
    only = tmp_path / "thing.py"
    only.write_text("class NotMatching:\n    pass\n", encoding="utf-8")
    assert _guess_class_name(only, "thing") == "NotMatching"


def test_extract_unreadable(tmp_path: Path) -> None:
    missing = tmp_path / "nope.py"
    assert extract_model_columns(missing) == {"id": "Any"}


def test_tuple_and_casts_helpers() -> None:
    assert _tuple_strings("x = 1", "fillable") == []
    assert _dict_casts("casts = {}") == {}
    assert _dict_casts("nope") == {}


def test_generate_stubs_no_app(tmp_path: Path) -> None:
    result = generate_stubs(tmp_path)
    assert not result.ok
    assert "bootstrap" in (result.error or "")


def test_generate_stubs_progress() -> None:
    root = Path(__file__).resolve().parents[1] / "examples" / "progress"
    result = generate_stubs(root)
    assert result.ok
    assert result.model_files
    assert result.routes_file is not None
    assert result.routes_file.is_file()
    post = next(p for p in result.model_files if p.name == "post.pyi")
    text = post.read_text(encoding="utf-8")
    assert "class Post(Model):" in text
    assert "views: int" in text
    activity = next(p for p in result.model_files if p.name == "activity.pyi")
    assert "class Activity(Model):" in activity.read_text(encoding="utf-8")
    readme = result.output_dir / "README.md"
    assert readme.is_file()


def test_route_names_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    routes = tmp_path / "routes"
    routes.mkdir()
    (routes / "web.py").write_text(
        'router.get("/").name("fallback.home")\n',
        encoding="utf-8",
    )

    class FakeIndex:
        ok = False
        routes: dict = {}

    monkeypatch.setattr("almasix.ide.stubs.build_index", lambda _root: FakeIndex())
    names = _route_names(tmp_path)
    assert "fallback.home" in names


def test_install_no_app(tmp_path: Path) -> None:
    result = install_editor_config(tmp_path)
    assert not result.ok
    assert "bootstrap" in (result.error or "")


def test_install_writes_vscode_and_jetbrains(tmp_path: Path) -> None:
    (tmp_path / "bootstrap").mkdir()
    (tmp_path / "bootstrap" / "app.py").write_text("# app\n", encoding="utf-8")
    # Put a fake grammar on the walk-up path.
    grammar_dir = tmp_path / "editors" / "prism" / "syntaxes"
    grammar_dir.mkdir(parents=True)
    grammar = grammar_dir / "prism.tmLanguage.json"
    grammar.write_text("{}", encoding="utf-8")

    result = install_editor_config(tmp_path, force=True)
    assert result.ok
    assert any(p.name == "extensions.json" for p in result.written)
    assert any(p.name == "settings.json" for p in result.written)
    assert any(p.name == "almasix-editor.md" for p in result.written)
    settings = json.loads((tmp_path / ".vscode" / "settings.json").read_text(encoding="utf-8"))
    assert settings["files.associations"]["*.prism.html"] == "prism-html"
    assert any("Prism TextMate grammar" in n for n in result.notes)

    # Second run without force keeps files.
    again = install_editor_config(tmp_path, force=False)
    assert again.ok
    assert any("Kept existing" in n for n in again.notes)


def test_install_skips_flags(tmp_path: Path) -> None:
    (tmp_path / "bootstrap").mkdir()
    (tmp_path / "bootstrap" / "app.py").write_text("#\n", encoding="utf-8")
    result = install_editor_config(tmp_path, vscode=False, jetbrains=False)
    assert result.ok
    assert not (tmp_path / ".vscode").exists()
    assert not list(result.written)


def test_merge_settings(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"editor.tabSize": 2}), encoding="utf-8")
    merged = _merge_settings(path)
    assert merged is not None
    assert "files.associations" in merged
    assert merged["editor.tabSize"] == 2

    path.write_text("{not-json", encoding="utf-8")
    assert _merge_settings(path) is not None

    path.write_text("[]", encoding="utf-8")
    assert isinstance(_merge_settings(path), dict)

    full = {
        "files.associations": {"*.prism.html": "prism-html"},
        "emmet.includeLanguages": {"prism-html": "html"},
        "[prism-html]": {"editor.formatOnSave": True},
        "almasix.pythonPath": "x",
    }
    path.write_text(json.dumps(full), encoding="utf-8")
    assert _merge_settings(path) is None

    partial = {"files.associations": {"*.md": "markdown"}}
    path.write_text(json.dumps(partial), encoding="utf-8")
    merged2 = _merge_settings(path)
    assert merged2 is not None
    assert merged2["files.associations"]["*.prism.html"] == "prism-html"


def test_write_vscode_merge_path(tmp_path: Path) -> None:
    result = IdeInstallResult(base_path=tmp_path)
    vscode = tmp_path / ".vscode"
    vscode.mkdir()
    (vscode / "extensions.json").write_text("{}", encoding="utf-8")
    (vscode / "settings.json").write_text(json.dumps({"x": 1}), encoding="utf-8")
    _write_vscode(tmp_path, result, force=False)
    assert any(p.name == "settings.json" for p in result.written)


def test_write_jetbrains_keep(tmp_path: Path) -> None:
    result = IdeInstallResult(base_path=tmp_path)
    idea = tmp_path / ".idea"
    idea.mkdir()
    note = idea / "almasix-editor.md"
    note.write_text("keep\n", encoding="utf-8")
    _write_jetbrains_note(tmp_path, result, force=False)
    assert note.read_text(encoding="utf-8") == "keep\n"
    assert any("Kept existing" in n for n in result.notes)


def test_locate_grammar_none(tmp_path: Path) -> None:
    assert _locate_grammar(tmp_path) is None


def test_stub_result_ok() -> None:
    bad = StubResult(base_path=Path("."), output_dir=Path("."), error="x")
    assert not bad.ok
    good = StubResult(base_path=Path("."), output_dir=Path("."))
    assert good.ok


def test_commands_handle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from almasix.ide.commands.install import IdeInstallCommand
    from almasix.ide.commands.stubs import IdeStubsCommand

    (tmp_path / "bootstrap").mkdir()
    (tmp_path / "bootstrap" / "app.py").write_text("#\n", encoding="utf-8")
    (tmp_path / "app" / "models").mkdir(parents=True)
    (tmp_path / "app" / "models" / "item.py").write_text(
        'class Item:\n    fillable = ("name",)\n',
        encoding="utf-8",
    )
    (tmp_path / "routes").mkdir()
    (tmp_path / "routes" / "web.py").write_text(
        'x.name("items.index")\n',
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    stubs_cmd = IdeStubsCommand()
    assert stubs_cmd.handle() == IdeStubsCommand.SUCCESS

    install_cmd = IdeInstallCommand()
    assert install_cmd.handle() == IdeInstallCommand.SUCCESS


def test_commands_failure_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from almasix.ide.commands.install import IdeInstallCommand
    from almasix.ide.commands.stubs import IdeStubsCommand

    monkeypatch.chdir(tmp_path)
    stubs = IdeStubsCommand()
    stubs._options = {"path": str(tmp_path)}
    assert stubs.handle() == IdeStubsCommand.FAILURE

    install = IdeInstallCommand()
    install._options = {"path": str(tmp_path)}
    assert install.handle() == IdeInstallCommand.FAILURE


def test_commands_relative_paths_outside_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cover relative_to ValueError branches when output is outside the app."""
    from almasix.ide.commands.install import IdeInstallCommand
    from almasix.ide.commands.stubs import IdeStubsCommand

    (tmp_path / "bootstrap").mkdir()
    (tmp_path / "bootstrap" / "app.py").write_text("#\n", encoding="utf-8")
    (tmp_path / "app" / "models").mkdir(parents=True)
    (tmp_path / "app" / "models" / "item.py").write_text(
        'class Item:\n    fillable = ("name",)\n',
        encoding="utf-8",
    )
    outside = Path("/tmp") / f"almasix-ide-stubs-{tmp_path.name}"
    stubs = IdeStubsCommand()
    stubs._options = {"path": str(tmp_path), "output": str(outside)}
    assert stubs.handle() == IdeStubsCommand.SUCCESS
    # Cleanup generated outside dir
    import shutil

    shutil.rmtree(outside, ignore_errors=True)

    # Install with written paths that can't relativize: monkeypatch result.
    install = IdeInstallCommand()
    install._options = {"path": str(tmp_path), "force": True}

    class FakeResult:
        ok = True
        error = None
        base_path = tmp_path
        written = [Path("/tmp/absolute-outside-almasix-ide")]
        notes = ["n"]

    monkeypatch.setattr(
        "almasix.ide.commands.install.install_editor_config",
        lambda *a, **k: FakeResult(),
    )
    assert install.handle() == IdeInstallCommand.SUCCESS


def test_commands_options_flags(tmp_path: Path) -> None:
    from almasix.ide.commands.install import IdeInstallCommand
    from almasix.ide.commands.stubs import IdeStubsCommand

    (tmp_path / "bootstrap").mkdir()
    (tmp_path / "bootstrap" / "app.py").write_text("#\n", encoding="utf-8")
    out = tmp_path / "custom-stubs"
    stubs = IdeStubsCommand()
    stubs._options = {"path": str(tmp_path), "output": str(out)}
    assert stubs.handle() == IdeStubsCommand.SUCCESS
    assert out.is_dir()

    install = IdeInstallCommand()
    install._options = {
        "path": str(tmp_path),
        "force": True,
        "no_vscode": True,
        "no_jetbrains": False,
    }
    assert install.handle() == IdeInstallCommand.SUCCESS
    assert not (tmp_path / ".vscode").exists()
    assert (tmp_path / ".idea" / "almasix-editor.md").is_file()


def test_commands_error_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    from almasix.ide.commands.install import IdeInstallCommand
    from almasix.ide.commands.stubs import IdeStubsCommand

    class Bad:
        ok = False
        error = None
        output_dir = Path(".")
        model_files: list = []
        routes_file = None
        written: list = []
        notes: list = []
        base_path = Path(".")

    monkeypatch.setattr("almasix.ide.commands.stubs.generate_stubs", lambda *a, **k: Bad())
    assert IdeStubsCommand().handle() == IdeStubsCommand.FAILURE

    monkeypatch.setattr("almasix.ide.commands.install.install_editor_config", lambda *a, **k: Bad())
    assert IdeInstallCommand().handle() == IdeInstallCommand.FAILURE
