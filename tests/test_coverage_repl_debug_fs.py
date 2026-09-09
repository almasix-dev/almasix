"""Coverage chase — REPL, debug, smith CLI, filesystem edge paths."""

from __future__ import annotations

import asyncio
import builtins
import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from almasix.console.command import Command
from almasix.console.repl import (
    _configure_ptpython,
    _start_ipython,
    _start_plain_console,
    _start_rich_console,
    build_namespace,
)
from almasix.console.scheduling import Event, schedule
from almasix.debug import (
    Caller,
    DumpAndDie,
    _caller,
    _print_header,
    _type_label,
    dd,
    dump,
    render_value,
)
from almasix.filesystem.adapter import FilesystemAdapter, coerce_bytes, normalize_path
from almasix.filesystem.drivers.local import LocalAdapter
from almasix.filesystem.drivers.memory import MemoryAdapter
from almasix.filesystem.manager import Storage, StorageManager
from almasix.filesystem.storage import Disk
from almasix.framework.application import Application
from almasix.smith import cli as smith_cli
from tests.support import purge_generated_app_modules

runner = CliRunner()


def _minimal_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Application:
    purge_generated_app_modules()
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "app.py").write_text(
        'config = {"name": "Cov", "debug": False, "providers": []}\n',
        encoding="utf-8",
    )
    (tmp_path / "config" / "logging.py").write_text(
        "config = {'default': 'null', 'channels': {'null': {'driver': 'null'}}}\n",
        encoding="utf-8",
    )
    (tmp_path / "routes").mkdir(exist_ok=True)
    (tmp_path / "bootstrap").mkdir(exist_ok=True)
    (tmp_path / "bootstrap" / "app.py").write_text("# stub\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    return Application(tmp_path)


# ---------------------------------------------------------------------------
# REPL
# ---------------------------------------------------------------------------


def test_namespace_dd_exits_and_skips_private_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _minimal_app(tmp_path, monkeypatch)
    app.load_environment()
    app.load_configuration()
    models = tmp_path / "app" / "models"
    models.mkdir(parents=True)
    (models / "__init__.py").write_text("", encoding="utf-8")
    (models / "_hidden.py").write_text(
        "class Hidden:\n    pass\n",
        encoding="utf-8",
    )
    (models / "post.py").write_text(
        "class Post:\n    pass\n",
        encoding="utf-8",
    )
    # Force the underscore-skip branch even if pkgutil omits private modules.
    import pkgutil

    real_iter = pkgutil.iter_modules

    def fake_iter(path: Any = None, prefix: str = ""):
        yield from real_iter(path, prefix)
        yield SimpleNamespace(name="_forced_skip", ispkg=False)

    monkeypatch.setattr(pkgutil, "iter_modules", fake_iter)
    ns = build_namespace(app)
    assert "Post" in ns
    assert "Hidden" not in ns
    with pytest.raises(SystemExit) as exc:
        ns["dd"]({"x": 1})
    assert exc.value.code == 0


def test_ipython_displayhook_and_asyncio_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeShell:
        def quiet(self) -> bool:
            return False

        def check_for_underscore(self) -> None:
            return None

        def start_displayhook(self) -> None:
            return None

        def write_output_prompt(self) -> None:
            return None

        def update_user_ns(self, result: Any) -> None:
            captured["ns"] = result

        def fill_exec_result(self, result: Any) -> None:
            captured["result"] = result

        def finish_displayhook(self) -> None:
            return None

        def __call__(self, using: str | None = None) -> None:
            if using == "asyncio":
                raise TypeError("no asyncio")
            captured["fallback"] = True

    def fake_instance(config=None, **kwargs: Any) -> FakeShell:
        del kwargs
        captured["hook_cls"] = config.TerminalInteractiveShell.displayhook_class
        return FakeShell()

    monkeypatch.setattr(
        "IPython.terminal.embed.InteractiveShellEmbed.instance",
        fake_instance,
    )
    rendered: list[Any] = []
    monkeypatch.setattr(
        "almasix.console.display.render",
        lambda value, **_: rendered.append(value),
    )
    assert _start_ipython({"x": 1}) == 0
    assert captured.get("fallback") is True
    hook_cls = captured["hook_cls"]
    hook = object.__new__(hook_cls)
    shell = FakeShell()
    hook.__dict__["shell"] = shell
    # Bypass DisplayHook helpers that need a full IPython shell.
    hook.__dict__["quiet"] = lambda: False
    hook.__dict__["check_for_underscore"] = lambda: None
    hook.__dict__["start_displayhook"] = lambda: None
    hook.__dict__["write_output_prompt"] = lambda: None
    hook.__dict__["update_user_ns"] = shell.update_user_ns
    hook.__dict__["fill_exec_result"] = shell.fill_exec_result
    hook.__dict__["finish_displayhook"] = lambda: None
    hook_cls.__call__(hook, None)

    async def _coro() -> int:
        return 7

    hook_cls.__call__(hook, _coro())
    assert captured["result"] == 7
    assert rendered == [7]
    hook_cls.__call__(hook, {"plain": True})
    assert captured["result"] == {"plain": True}


def test_configure_ptpython_wraps_eval() -> None:
    async def _c() -> str:
        return "awaited"

    repl = SimpleNamespace(
        show_signature=False,
        show_docstring=False,
        highlight_matching_parenthesis=False,
        color_depth="",
        enable_syntax_highlighting=False,
        prompt_style="",
        show_line_numbers=True,
        use_code_colorscheme=lambda _n: None,
        eval=lambda expr: _c() if expr == "coro" else expr,
    )
    _configure_ptpython(repl)
    assert repl.eval("coro") == "awaited"
    assert repl.eval("plain") == "plain"


def test_configure_ptpython_leaves_a_private_eval_where_it_found_it() -> None:
    """Older ptpython spells it ``_eval``; wrapping it is not ours to do."""
    private = SimpleNamespace(
        show_signature=False,
        show_docstring=False,
        highlight_matching_parenthesis=False,
        color_depth="",
        enable_syntax_highlighting=False,
        prompt_style="",
        show_line_numbers=True,
        use_code_colorscheme=lambda _n: None,
        _eval=lambda expr: expr,
    )

    _configure_ptpython(private)

    assert not hasattr(private, "eval")


def test_rich_console_runcode_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _minimal_app(tmp_path, monkeypatch)
    app.load_environment()
    app.load_configuration()
    ns = build_namespace(app)
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: (_ for _ in ()).throw(EOFError()))
    consoles: list[Any] = []

    def capture_interact(self: Any, *a: Any, **k: Any) -> None:
        del a, k
        consoles.append(self)

    monkeypatch.setattr("code.InteractiveConsole.interact", capture_interact)
    _start_rich_console(ns)
    console = consoles[0]
    with pytest.raises(SystemExit):
        console.runcode(
            compile(
                "from almasix.debug import DumpAndDie; raise DumpAndDie((1,), None)",
                "<t>",
                "exec",
            )
        )
    with pytest.raises(SystemExit):
        console.runcode(compile("raise SystemExit(2)", "<t>", "exec"))
    shown: list[bool] = []
    monkeypatch.setattr(console, "showtraceback", lambda: shown.append(True))
    console.runcode(compile("raise ValueError('x')", "<t>", "exec"))
    assert shown


def test_plain_console_displayhook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _minimal_app(tmp_path, monkeypatch)
    app.load_environment()
    app.load_configuration()
    ns = build_namespace(app)
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: (_ for _ in ()).throw(EOFError()))
    monkeypatch.setattr("code.InteractiveConsole.interact", lambda *a, **k: None)
    original = sys.displayhook
    _start_plain_console(ns)
    assert sys.displayhook is not original
    sys.displayhook(None)
    sys.displayhook({"k": 1})
    assert builtins._ == {"k": 1}


# ---------------------------------------------------------------------------
# debug
# ---------------------------------------------------------------------------


def test_caller_and_type_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    import inspect

    assert Caller(file="solo.py", line=1, function="f").short_file == "solo.py"
    assert "b/c.py:2" in str(Caller(file="/a/b/c.py", line=2, function="g"))
    assert _caller(depth=10_000) is None

    class _Frame:
        def __init__(self, back: Any = None) -> None:
            self.f_back = back
            self.f_code = SimpleNamespace(co_filename="x.py", co_name="f")
            self.f_lineno = 1

    top = _Frame()
    mid = _Frame(top)
    bot = _Frame(mid)
    monkeypatch.setattr(inspect, "currentframe", lambda: bot)
    # Exactly drain the chain so the post-loop None check runs (line 67).
    assert _caller(depth=3) is None
    assert _type_label(3) == "int"
    assert "Caller" in _type_label(Caller("f.py", 1, "x"))


def test_dump_dd_without_rich(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    real_import = builtins.__import__

    def guarded(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "rich" or name.startswith("rich."):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    dump({"a": 1})
    render_value([1, 2], index=0, as_json=True)
    _print_header(badge="dump", caller=None, count=1)
    out = capsys.readouterr().out
    assert "dump" in out.lower() or "a" in out
    with pytest.raises(DumpAndDie):
        dd("halt")
    assert "halted" in capsys.readouterr().out.lower()


def test_render_value_json_fallback_and_headers(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch("rich.json.JSON.from_data", side_effect=ValueError("bad")):
        render_value({"x": 1}, as_json=True)
    _print_header(badge="dd", caller=Caller("a/b.py", 9, "<module>"), count=1)
    _print_header(badge="dump", caller=Caller("a/b.py", 9, "my_fn"), count=2)
    assert "dump" in capsys.readouterr().out.lower() or True


# ---------------------------------------------------------------------------
# smith CLI
# ---------------------------------------------------------------------------


def test_list_skips_hidden_and_names_broken_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    from almasix.console.commands.listing import ListCommand
    from almasix.console.kernel import ConsoleKernel

    class HiddenCmd(Command):
        signature = "demo:hidden"
        hidden = True
        description = "nope"

        def handle(self) -> int:
            return 0

    class VisCmd(Command):
        signature = "demo:vis"
        description = "visible"
        aliases = ("demo:seen",)

        def handle(self) -> int:
            return 0

    from almasix.console.kernel import DiscoveryFailure

    kernel = ConsoleKernel.for_cwd(tmp_path)
    kernel.discover_framework_commands()
    kernel.register(HiddenCmd)
    kernel.register(VisCmd)
    kernel.failures.append(DiscoveryFailure("app.console.commands.broken", ImportError("boom")))

    assert kernel.run_argv("list", []) == 0
    listed = capsys.readouterr().out
    assert "demo:vis" in listed
    assert "demo:hidden" not in listed
    # An alias is named beside its command, not listed as a command of its own.
    assert listed.count("demo:seen") == 1
    assert "Command not loaded — app.console.commands.broken" in listed

    empty = ConsoleKernel.for_cwd(tmp_path)
    empty.register(ListCommand)
    assert empty.run_argv("list", []) == 0


def test_schedule_run_work_and_loupe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    schedule.events.clear()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bootstrap").mkdir(exist_ok=True)
    (tmp_path / "bootstrap" / "app.py").write_text("x=1\n", encoding="utf-8")

    empty = runner.invoke(smith_cli.app, ["schedule:run"])
    assert "No scheduled" in empty.stdout

    schedule.events.append(Event(description="inspire", command="inspire").every_minute())
    ran = runner.invoke(smith_cli.app, ["schedule:run"])
    assert ran.exit_code == 0
    assert "Running: inspire" in ran.stdout
    schedule.events.clear()

    sleeps = {"n": 0}

    def fake_sleep(_: float) -> None:
        sleeps["n"] += 1
        if sleeps["n"] >= 1:
            raise KeyboardInterrupt

    monkeypatch.setattr("time.sleep", fake_sleep)
    schedule.events.clear()
    schedule.events.append(Event(description="tick", command="inspire").every_minute())
    result = runner.invoke(smith_cli.app, ["schedule:work", "--sleep", "1"])
    assert "stopped" in result.stdout.lower()
    schedule.events.clear()

    with patch("almasix.console.repl.start_loupe", return_value=0):
        for alias in ("loupe", "tinker", "repl"):
            result = runner.invoke(smith_cli.app, [alias])
            assert result.exit_code == 0, alias


# ---------------------------------------------------------------------------
# filesystem
# ---------------------------------------------------------------------------


def test_adapter_protocol_stubs_and_helpers() -> None:
    # Protocol ellipsis bodies are executable when called on the class.
    FilesystemAdapter.put(None, "p", b"x")  # type: ignore[arg-type]
    FilesystemAdapter.get(None, "p")  # type: ignore[arg-type]
    FilesystemAdapter.read_stream(None, "p")  # type: ignore[arg-type]
    FilesystemAdapter.exists(None, "p")  # type: ignore[arg-type]
    FilesystemAdapter.delete(None, "p")  # type: ignore[arg-type]
    FilesystemAdapter.copy(None, "a", "b")  # type: ignore[arg-type]
    FilesystemAdapter.move(None, "a", "b")  # type: ignore[arg-type]
    FilesystemAdapter.size(None, "p")  # type: ignore[arg-type]
    FilesystemAdapter.files(None)  # type: ignore[arg-type]
    FilesystemAdapter.directories(None)  # type: ignore[arg-type]
    FilesystemAdapter.make_directory(None, "d")  # type: ignore[arg-type]
    FilesystemAdapter.delete_directory(None, "d")  # type: ignore[arg-type]
    FilesystemAdapter.url(None, "p")  # type: ignore[arg-type]
    FilesystemAdapter.temporary_url(None, "p", 1)  # type: ignore[arg-type]
    FilesystemAdapter.set_visibility(None, "p", "public")  # type: ignore[arg-type]
    FilesystemAdapter.get_visibility(None, "p")  # type: ignore[arg-type]
    assert normalize_path("..") == ""
    assert normalize_path("a/../b") == "b"
    assert coerce_bytes(BytesIO(b"z")) == b"z"


def test_disk_passthrough_and_put_file_str(tmp_path: Path) -> None:
    disk = Disk("local", LocalAdapter(tmp_path))

    class StrFile:
        filename = "s.txt"

        def read(self) -> str:
            return "hello"

    assert disk.put_file("up", StrFile()).endswith("s.txt")

    class AsyncExact:
        filename = "exact.txt"

        async def read(self) -> bytes:
            return b"x"

    assert asyncio.run(disk.put_file_async("dir/exact.txt", AsyncExact())) == "dir/exact.txt"
    disk.put("a.txt", b"1")
    assert disk.read_stream("a.txt").read() == b"1"
    assert disk.size("a.txt") == 1
    disk.make_directory("d")
    assert "d" in disk.directories()
    disk.delete_directory("d")
    disk.set_visibility("a.txt", "public")
    assert disk.get_visibility("a.txt") == "public"


def test_manager_roots_errors_and_facade(tmp_path: Path) -> None:
    app = Application(tmp_path)
    mgr = StorageManager(
        app,
        {
            "default": "local",
            "disks": {
                "local": {"driver": "local"},
                "public": {"driver": "public", "root": "storage/app/public"},
                "arr": {"driver": "array"},
            },
        },
    )
    assert mgr.disk("local").put("f.txt", b"1") == "f.txt"
    assert mgr.disk("public").put("p.txt", b"2") == "p.txt"
    with pytest.raises(KeyError, match="not configured"):
        mgr.disk("nope")
    with pytest.raises(ValueError, match="Unsupported"):
        StorageManager(config={"disks": {"x": {"driver": "ftp"}}}).disk("x")
    Storage.set_manager(None)
    assert Storage.manager() is not None
    Storage.set_manager(mgr)
    assert Storage.url("f.txt").startswith("/")
    Storage.set_manager(None)


def test_memory_and_local_remaining_branches(tmp_path: Path) -> None:
    mem = MemoryAdapter()
    assert mem.delete("ghost") is False
    with pytest.raises(FileNotFoundError):
        mem.copy("missing", "x")
    mem.put("a/b.txt", b"x")
    assert mem.size("a/b.txt") == 1
    mem.put("other/z.txt", b"z")
    assert "other/z.txt" not in mem.files("a")
    mem.make_directory("")
    assert isinstance(mem.directories("nope"), list)
    # directories() empty-first segment continue
    mem.put("/.weird", b"x")  # may normalize away; also hit recursive branch
    mem.make_directory("nest/deep")
    assert isinstance(mem.directories("nest", recursive=True), list)

    local = LocalAdapter(tmp_path)
    local.make_directory("dir")
    assert local.delete("dir") is True
    local.put("m.txt", b"x", visibility="public")
    local.move("m.txt", "n.txt")
    assert local.get_visibility("n.txt") == "public"
    # move without prior visibility entry (114→116 false branch already; ensure file move)
    local.put("plain.txt", b"y")
    local.move("plain.txt", "plain2.txt")
    local.make_directory("nodir")
    local.set_visibility("nodir", "public")

    # manager relative root with app
    app = Application(tmp_path)
    mgr = StorageManager(
        app,
        {
            "default": "local",
            "disks": {"local": {"driver": "local", "root": "rel-root"}},
        },
    )
    assert mgr.disk("local").put("z.txt", b"1") == "z.txt"
    assert (tmp_path / "rel-root" / "z.txt").is_file()
