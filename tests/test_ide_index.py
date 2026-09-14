"""Unit tests for ``smith ide:index`` / ``almasix.ide.index``."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

from almasix.ide import __main__ as ide_main
from almasix.ide.commands.index import IdeIndexCommand
from almasix.ide.index import (
    _pathish,
    _returns_relation,
    _string_dict,
    _string_list,
    attach_models_to_tables,
    build_ide_index,
    discover_components,
    discover_config_slices,
    discover_gates,
    discover_inertia_pages,
    discover_model_metadata,
    dump_index_json,
    index_to_dict,
)
from almasix.lsp.index import AppIndex, build_index

PROGRESS = Path(__file__).resolve().parents[1] / "examples" / "progress"


def test_build_ide_index_progress() -> None:
    payload = build_ide_index(PROGRESS)
    assert payload["ok"] is True
    assert payload["error"] is None
    assert len(payload["views"]) >= 1
    assert len(payload["config_keys"]) >= 1
    assert len(payload["validation_rules"]) >= 50
    assert "required" in payload["validation_rules"]
    assert len(payload["smith_commands"]) >= 20
    assert "ide:index" in payload["smith_commands"]
    assert "serve" in payload["smith_commands"]
    assert isinstance(payload["gates"], list)
    assert isinstance(payload["components"], dict)
    assert isinstance(payload["casts"], list)
    assert "int" in payload["casts"]
    assert isinstance(payload["directives"], list)
    assert "if" in payload["directives"]
    locations = payload["config_locations"]
    assert isinstance(locations, dict)
    assert "app.env" in locations
    assert locations["app.env"]["path"].endswith("config/app.py")
    assert isinstance(locations["app.env"]["line"], int)
    assert locations["app.env"]["line"] >= 0
    # Spot-check the AST line against the source file
    app_py = Path(locations["app.env"]["path"])
    line_text = app_py.read_text(encoding="utf-8").splitlines()[locations["app.env"]["line"]]
    assert '"env"' in line_text or "'env'" in line_text
    assert "QUEUE_CONNECTION" in payload["env_options"]
    assert "redis" in payload["env_options"]["QUEUE_CONNECTION"]
    data = json.loads(dump_index_json(PROGRESS))
    assert data["ok"] is True
    assert data["base_path"] == str(PROGRESS.resolve())
    assert "app.env" in data["config_locations"]
    assert "QUEUE_CONNECTION" in data["env_options"]


def test_ide_index_cli_json() -> None:
    result = subprocess.run(
        [sys.executable, "smith", "ide:index", "--json", "--path", str(PROGRESS)],
        cwd=PROGRESS,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert "routes" in payload
    assert "validation_rules" in payload


def test_ide_index_human() -> None:
    result = subprocess.run(
        [sys.executable, "smith", "ide:index", "--path", str(PROGRESS)],
        cwd=PROGRESS,
        capture_output=True,
        text=True,
        check=False,
    )
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    assert "ide:index ok" in out
    assert "views" in out


def test_ide_index_command_handle_json(monkeypatch) -> None:
    lines: list[str] = []
    cmd = IdeIndexCommand()
    cmd._options = {"path": str(PROGRESS), "json": True}
    monkeypatch.setattr(cmd, "line", lambda msg="": lines.append(str(msg)))
    monkeypatch.setattr(cmd, "info", lambda msg="": lines.append(str(msg)))
    monkeypatch.setattr(cmd, "error", lambda msg="": lines.append(f"ERR:{msg}"))
    assert cmd.handle() == IdeIndexCommand.SUCCESS
    assert any('"ok"' in line for line in lines)


def test_ide_index_command_handle_human(monkeypatch) -> None:
    lines: list[str] = []
    cmd = IdeIndexCommand()
    cmd._options = {"path": str(PROGRESS), "json": False}
    monkeypatch.setattr(cmd, "line", lambda msg="": lines.append(str(msg)))
    monkeypatch.setattr(cmd, "info", lambda msg="": lines.append(str(msg)))
    monkeypatch.setattr(cmd, "error", lambda msg="": lines.append(f"ERR:{msg}"))
    assert cmd.handle() == IdeIndexCommand.SUCCESS
    assert any("ide:index ok" in line for line in lines)


def test_ide_index_command_failure_json(monkeypatch) -> None:
    lines: list[str] = []
    cmd = IdeIndexCommand()
    cmd._options = {"path": "/tmp", "json": True}
    monkeypatch.setattr(
        "almasix.ide.commands.index.build_ide_index",
        lambda base=None: {"ok": False, "error": "No app", "base_path": str(base)},
    )
    monkeypatch.setattr(cmd, "line", lambda msg="": lines.append(str(msg)))
    monkeypatch.setattr(cmd, "info", lambda msg="": lines.append(str(msg)))
    monkeypatch.setattr(cmd, "error", lambda msg="": lines.append(f"ERR:{msg}"))
    assert cmd.handle() == IdeIndexCommand.FAILURE
    assert any(line.startswith("ERR:") for line in lines)
    assert any('"ok"' in line for line in lines)


def test_ide_index_command_failure_human(monkeypatch) -> None:
    lines: list[str] = []
    cmd = IdeIndexCommand()
    cmd._options = {"json": False}
    monkeypatch.setattr(
        "almasix.ide.commands.index.build_ide_index",
        lambda base=None: {"ok": False, "error": None},
    )
    monkeypatch.setattr(cmd, "line", lambda msg="": lines.append(str(msg)))
    monkeypatch.setattr(cmd, "info", lambda msg="": lines.append(str(msg)))
    monkeypatch.setattr(cmd, "error", lambda msg="": lines.append(f"ERR:{msg}"))
    assert cmd.handle() == IdeIndexCommand.FAILURE
    assert any("Index failed" in line for line in lines)


def test_ide_main_module(capsys) -> None:
    code = ide_main.main(["--path", str(PROGRESS)])
    assert code == 0
    out = capsys.readouterr().out
    assert '"ok"' in out


def test_discover_helpers(tmp_path: Path) -> None:
    models_dir = tmp_path / "app" / "models"
    models_dir.mkdir(parents=True)
    model = models_dir / "post.py"
    model.write_text(
        "class Post:\n"
        "    fillable = ['title', 'body']\n"
        "    casts = {'id': 'int', 'meta': 'array'}\n"
        "    def author(self):\n"
        "        return self.belongs_to(User)\n"
        "    async def comments(self):\n"
        "        return self.has_many(Comment)\n"
        "    def _private(self):\n"
        "        return self.has_many(X)\n",
        encoding="utf-8",
    )
    meta = discover_model_metadata({"post": model})
    assert "Post" in meta
    assert meta["Post"]["fillable"] == ["title", "body"]
    assert meta["Post"]["casts"]["id"] == "int"
    assert meta["Post"].get("guarded") == []
    assert meta["Post"].get("hidden") == []
    assert "author" in meta["Post"]["relations"]
    assert "comments" in meta["Post"]["relations"]

    guarded_model = models_dir / "account.py"
    guarded_model.write_text(
        "class Account:\n"
        "    fillable = ['name']\n"
        "    guarded = ['balance']\n"
        "    hidden = ['token']\n",
        encoding="utf-8",
    )
    gmeta = discover_model_metadata({"account": guarded_model})
    assert gmeta["Account"]["guarded"] == ["balance"]
    assert gmeta["Account"]["hidden"] == ["token"]

    annotated = models_dir / "author.py"
    annotated.write_text(
        "class Author:\n"
        "    guarded: tuple[str, ...] = ('id',)\n"
        "    fillable: tuple[str, ...] = ('name',)\n"
        "    hidden: tuple[str, ...] = ('secret',)\n",
        encoding="utf-8",
    )
    ameta = discover_model_metadata({"author": annotated})
    assert ameta["Author"]["guarded"] == ["id"]
    assert ameta["Author"]["fillable"] == ["name"]
    assert ameta["Author"]["hidden"] == ["secret"]

    bare = models_dir / "note.py"
    bare.write_text(
        "class Note:\n    guarded: tuple[str, ...] = ('id')\n",
        encoding="utf-8",
    )
    bmeta = discover_model_metadata({"note": bare})
    assert bmeta["Note"]["guarded"] == ["id"]

    bad = models_dir / "broken.py"
    bad.write_text("class Broken(:\n", encoding="utf-8")
    assert discover_model_metadata({"broken": bad}) == {}

    components_dir = tmp_path / "resources" / "views" / "components"
    components_dir.mkdir(parents=True)
    (components_dir / "alert.prism.html").write_text("x", encoding="utf-8")
    class_dir = tmp_path / "app" / "view" / "components"
    class_dir.mkdir(parents=True)
    (class_dir / "alert_banner.py").write_text(
        "class AlertBanner:\n    pass\n",
        encoding="utf-8",
    )
    comps = discover_components(tmp_path)
    assert "alert" in comps
    assert "alert-banner" in comps

    pages = tmp_path / "resources" / "js" / "Pages" / "Dashboard"
    pages.mkdir(parents=True)
    (pages / "Index.vue").write_text("<template></template>", encoding="utf-8")
    (pages / "notes.txt").write_text("skip", encoding="utf-8")
    assert "Dashboard/Index" in discover_inertia_pages(tmp_path)

    lower = tmp_path / "other"
    lower_pages = lower / "resources" / "js" / "pages"
    lower_pages.mkdir(parents=True)
    (lower_pages / "Home.jsx").write_text("export default {}", encoding="utf-8")
    assert "Home" in discover_inertia_pages(lower)

    assert discover_inertia_pages(tmp_path / "empty") == []

    slices = discover_config_slices(
        (
            "filesystems.disks.local.driver",
            "filesystems.disks.default",
            "queue.connections.sync.driver",
            "cache.stores.file.driver",
            "mail.mailers.smtp.transport",
            "app.name",
        )
    )
    assert "local" in slices["disks"]
    assert "sync" in slices["queues"]
    assert "file" in slices["caches"]
    assert "smtp" in slices["mailers"]


def test_discover_gates_from_policies(tmp_path: Path) -> None:
    policies = tmp_path / "app" / "policies"
    policies.mkdir(parents=True)
    (policies / "post_policy.py").write_text(
        "class PostPolicy:\n"
        "    def view(self, user, post): ...\n"
        "    def _hidden(self): ...\n"
        "    def before(self): ...\n",
        encoding="utf-8",
    )
    providers = tmp_path / "app" / "providers"
    providers.mkdir(parents=True)
    (providers / "auth_service_provider.py").write_text(
        'Gate.define("deploy", lambda user: True)\n',
        encoding="utf-8",
    )
    index = AppIndex(base_path=tmp_path, middleware_aliases=("web",))
    gates = discover_gates(tmp_path, index)
    assert "view" in gates
    assert "deploy" in gates
    assert "_hidden" not in gates


def test_ast_helpers_and_pathish() -> None:
    tree = ast.parse("fillable = ('a', 1)\ncasts = {'x': 'int', 2: 'y', 'z': 3}\n")
    assign = tree.body[0]
    assert isinstance(assign, ast.Assign)
    assert _string_list(assign.value) == ["a"]
    assert _string_list(ast.parse("x = 1").body[0].value) == []  # type: ignore[arg-type]
    assert _string_list(ast.parse("x = 'id'").body[0].value) == ["id"]  # type: ignore[arg-type]
    casts_assign = tree.body[1]
    assert isinstance(casts_assign, ast.Assign)
    assert _string_dict(casts_assign.value) == {"x": "int"}
    assert _string_dict(ast.parse("x = []").body[0].value) == {}  # type: ignore[arg-type]

    fn = ast.parse("def posts(self):\n    return has_many(Comment)\n").body[0]
    assert isinstance(fn, ast.FunctionDef)
    assert _returns_relation(fn) is True
    bare = ast.parse("def name(self):\n    return 1\n").body[0]
    assert isinstance(bare, ast.FunctionDef)
    assert _returns_relation(bare) is False

    assert _pathish(Path("/tmp/x")) == "/tmp/x"
    assert _pathish({"a": Path("/b")}) == {"a": "/b"}
    assert _pathish([Path("/c"), 1]) == ["/c", 1]
    assert _pathish(5) == 5


def test_attach_models_to_tables() -> None:
    tables = {
        "authors": {"name": "authors", "model": None, "columns": {}},
        "users": {"name": "users", "model": "User", "columns": {}},
    }
    attach_models_to_tables(tables, {"Author": {}, "User": {}})
    assert tables["authors"]["model"] == "Author"
    assert tables["users"]["model"] == "User"  # unchanged


def test_index_to_dict_with_error() -> None:
    index = AppIndex(base_path=Path("/tmp"), error="boom")
    payload = index_to_dict(index, extras={"gates": []})
    assert payload["ok"] is False
    assert payload["error"] == "boom"
    assert payload["gates"] == []


def test_build_index_then_extras_on_progress() -> None:
    index = build_index(PROGRESS)
    assert index.ok
    payload = index_to_dict(index)
    assert "views" in payload
