"""M9 coverage fill — exercise console package edge paths."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import typer

from almasix.console.command import Command, parse_signature
from almasix.console.kernel import ConsoleKernel, _parse_argv
from almasix.console.mutex import Mutex, sleep_until
from almasix.console.output import Output
from almasix.console.provider import ConsoleServiceProvider
from almasix.console.repl import BANNER, build_namespace, resolve_awaitable, run, start_loupe
from almasix.console.scheduling import Event, Schedule, _cron_matches, run_event, schedule
from almasix.framework import Application
from tests.support import purge_generated_app_modules


class FullCommand(Command):
    signature = "demo:full {name} {tags...} {--queue=default} {--force}"
    description = "Full signature demo"

    def handle(self) -> None:
        self.info("i")
        self.comment("c")
        self.warn("w")
        self.error("e")
        self.success("s")
        self.table(["a", "b"], [["1", "2"], ["3"]])
        assert self.confirm("ok?", default=True) is True
        self.line("done")


class ExitOneCommand(Command):
    signature = "demo:exit1"
    description = "Non-zero exit"

    def handle(self) -> int:
        return 1


class BrokenCommand(Command):
    signature = "demo:broken"

    def handle(self) -> int:
        raise RuntimeError("boom")


class NoSigCommand(Command):
    signature = ""


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


def test_parse_signature_errors_and_optional() -> None:
    with pytest.raises(ValueError, match="must include"):
        parse_signature("")
    with pytest.raises(ValueError, match="Invalid signature"):
        parse_signature("x {bad token}")
    name, args, opts = parse_signature("x {name?} {--flag}")
    assert name == "x"
    assert args[0]["optional"] is True
    assert opts[0]["is_flag"] is True


def test_command_helpers_and_unimplemented(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALMASIX_PROMPTS_INTERACTIVE", "0")
    cmd = FullCommand()
    assert (
        cmd.run(arguments={"name": "n", "tags": ["a"]}, options={"queue": "high", "force": True})
        == 0
    )
    with pytest.raises(NotImplementedError):
        Command().handle()
    assert NoSigCommand.name() == "NoSigCommand"


def test_output_helpers(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ALMASIX_PROMPTS_INTERACTIVE", "0")
    out = Output()
    out.line("l")
    out.info("i")
    out.comment("c")
    out.question("q")
    out.warn("w")
    out.error("e")
    out.success("s")
    out.new_line(2)
    out.table(["h"], [["r"], []])
    out.table(["a"], [["only", "extra"]])  # extra cell ignored
    out.table(["Method", "URI"], [["GET|HEAD", "/"]])
    out.title("Almasix")
    out.namespace("Usage:")
    out.two_column("inspire", "Display an inspiring quote", width=8)
    out.quote("Simplicity is the ultimate sophistication.", "Leonardo da Vinci")
    assert out.confirm("ok?", default=True) is True
    captured = capsys.readouterr()
    out_text = captured.out + captured.err
    assert "✔" in out_text and "s" in out_text
    assert "✘" in out_text and "e" in out_text
    assert "GET|HEAD" in out_text
    assert "inspire" in out_text
    assert "Leonardo da Vinci" in out_text


def test_parse_argv_flags_and_required() -> None:
    _, args_meta, opts_meta = parse_signature("x {name} {extra?} {--queue=default} {--force}")
    arguments, options = _parse_argv(
        ["Ada", "--force", "--queue", "high"],
        args_meta,
        opts_meta,
    )
    assert arguments["name"] == "Ada"
    assert arguments["extra"] is None
    assert options["force"] is True
    assert options["queue"] == "high"

    arguments, options = _parse_argv(["Bob", "--queue=low", "--force"], args_meta, opts_meta)
    assert arguments["name"] == "Bob"
    assert options["queue"] == "low"

    arguments, options = _parse_argv(["Eve", "--force"], args_meta, opts_meta)
    assert options["force"] is True

    # Unknown option without a following value becomes True
    arguments, options = _parse_argv(["Zoe", "--mystery"], args_meta, opts_meta)
    assert options["mystery"] is True

    with pytest.raises(typer.BadParameter):
        _parse_argv([], args_meta, opts_meta)

    _, variadic_meta, _ = parse_signature("x {tags...}")
    arguments, _ = _parse_argv(["a", "b"], variadic_meta, [])
    assert arguments["tags"] == ["a", "b"]

    _, opt_default, _ = parse_signature("x {name=world}")
    arguments, _ = _parse_argv([], opt_default, [])
    assert arguments["name"] == "world"


def test_kernel_paths_and_exceptions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _minimal_app(tmp_path, monkeypatch)
    app.load_environment()
    app.load_configuration()
    app.register_configured_providers()
    app.boot()
    kernel = ConsoleKernel(app)
    kernel.discover()
    kernel.register(NoSigCommand)
    assert "inspire" in kernel.commands

    cmds = tmp_path / "app" / "console" / "commands"
    cmds.mkdir(parents=True)
    (cmds / "__init__.py").write_text("", encoding="utf-8")
    (cmds / "local_hi.py").write_text(
        "from almasix.console import Command\n"
        "class LocalHi(Command):\n"
        "    signature = 'local:hi'\n"
        "    def handle(self):\n"
        "        self.line('hi')\n"
        "        return 0\n",
        encoding="utf-8",
    )
    kernel._load_path(cmds)
    assert "local:hi" in kernel.commands
    assert kernel.run_command("local:hi") == 0
    assert kernel.run_argv("local:hi", []) == 0

    with pytest.raises(KeyError):
        kernel.run_command("missing")
    with pytest.raises(KeyError):
        kernel.run_argv("missing", [])

    kernel.register(BrokenCommand)
    with pytest.raises(RuntimeError):
        kernel.run_command("demo:broken")

    (tmp_path / "routes" / "console.py").write_text(
        "from almasix.console import schedule\n"
        "schedule.call(lambda: None, description='noop').every_minute()\n",
        encoding="utf-8",
    )
    schedule.events.clear()
    kernel.load_console_routes()
    assert any(e.description == "noop" for e in schedule.events)
    schedule.events.clear()

    typer_app = typer.Typer()
    kernel.register_on_typer(typer_app)
    assert any(c.name == "inspire" for c in typer_app.registered_commands)


def test_kernel_report_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _minimal_app(tmp_path, monkeypatch)
    app.load_environment()
    app.load_configuration()
    kernel = ConsoleKernel(app)
    kernel._report_exception(RuntimeError("x"))

    # Handler.report itself failing is swallowed
    boom = MagicMock(side_effect=RuntimeError("report failed"))
    fake_handler = MagicMock()
    fake_handler.report = boom
    monkeypatch.setattr(
        "almasix.exceptions.handler.Handler",
        lambda *a, **k: fake_handler,
    )
    kernel._report_exception(RuntimeError("y"))


def test_kernel_import_and_missing_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _minimal_app(tmp_path, monkeypatch)
    app.load_environment()
    app.load_configuration()
    kernel = ConsoleKernel(app)
    kernel._load_package("almasix.console.commands.does_not_exist_pkg")
    kernel.load_console_routes()  # no routes/console.py yet

    with patch("importlib.util.spec_from_file_location", return_value=None):
        cmds = tmp_path / "app" / "console" / "commands"
        cmds.mkdir(parents=True, exist_ok=True)
        (cmds / "ghost.py").write_text("x = 1\n", encoding="utf-8")
        kernel._load_path(cmds)
        (tmp_path / "routes" / "console.py").write_text("x = 1\n", encoding="utf-8")
        kernel.load_console_routes()


def test_typer_attach_nonzero_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _minimal_app(tmp_path, monkeypatch)
    app.load_environment()
    app.load_configuration()
    app.register_configured_providers()
    app.boot()
    kernel = ConsoleKernel(app)
    kernel.register(ExitOneCommand)
    typer_app = typer.Typer()
    kernel.register_on_typer(typer_app)
    from typer.testing import CliRunner

    result = CliRunner().invoke(typer_app, ["demo:exit1"])
    assert result.exit_code == 1


def test_schedule_filters_and_runner(tmp_path: Path) -> None:
    weekday = datetime(2026, 9, 7, 0, 0, 0)  # Monday
    weekend = datetime(2026, 9, 5, 0, 0, 0)  # Saturday
    assert Event("d").daily().is_due(weekday)
    assert Event("f").every_five_minutes().is_due(datetime(2026, 9, 5, 10, 5, 0))
    assert Event("wd").cron("* * * * *").weekdays().is_due(weekday)
    assert not Event("wd").cron("* * * * *").weekdays().is_due(weekend)
    assert Event("wo").withoutOverlapping() is not None

    with pytest.raises(ValueError):
        _cron_matches("* * *", weekday)
    assert _cron_matches("0-5,10 * * * *", datetime(2026, 9, 5, 10, 3, 0))
    assert not _cron_matches("0-5,10 * * * *", datetime(2026, 9, 5, 10, 7, 0))

    held = Mutex(tmp_path, "busy")
    assert held.acquire()
    skipped = Event("busy", callback=lambda: None).every_minute().without_overlapping_lock()
    assert run_event(skipped, base_path=tmp_path) == 0
    held.release()

    seen: list[str] = []
    cmd_event = Event("inspire", command="inspire").every_minute()
    assert run_event(cmd_event, base_path=tmp_path, runner=lambda n: seen.append(n) or 7) == 7
    assert seen == ["inspire"]
    assert run_event(Event("empty"), base_path=tmp_path) == 0

    sched = Schedule()
    sched.command("inspire").hourly()
    assert sched.due_events(datetime(2026, 9, 5, 10, 0, 0))


def test_mutex_release_noop_and_sleep(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mutex = Mutex(tmp_path, "job/name!")
    mutex.release()
    sleep_until(0)
    assert mutex.acquire()
    monkeypatch.setattr("almasix.console.mutex.os.name", "nt")
    mutex.release()


def test_mutex_acquire_windows_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mutex = Mutex(tmp_path, "win")
    monkeypatch.setattr("almasix.console.mutex.os.name", "nt")

    class FakeMsvcrt:
        @staticmethod
        def locking(fd, mode, nbytes):
            return None

        LK_NBLCK = 1

    monkeypatch.setitem(__import__("sys").modules, "msvcrt", FakeMsvcrt())
    assert mutex.acquire() is True
    mutex.release()


def test_mutex_unlink_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mutex = Mutex(tmp_path, "x")
    assert mutex.acquire()
    monkeypatch.setattr(Path, "unlink", lambda *a, **k: (_ for _ in ()).throw(OSError("busy")))
    mutex.release()


def test_provider_binds_kernel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _minimal_app(tmp_path, monkeypatch)
    app.load_environment()
    app.load_configuration()
    ConsoleServiceProvider(app).register()
    ConsoleServiceProvider(app).boot()
    kernel = app.make(ConsoleKernel)
    assert isinstance(kernel, ConsoleKernel)
    assert "inspire" in kernel.commands


def test_resolve_awaitable_and_run() -> None:
    async def demo():
        return [1, 2, 3]

    assert resolve_awaitable(42) == 42
    assert resolve_awaitable(None) is None
    assert resolve_awaitable(demo()) == [1, 2, 3]
    assert run(demo()) == [1, 2, 3]


def test_repl_namespace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _minimal_app(tmp_path, monkeypatch)
    app.load_environment()
    app.load_configuration()
    ns = build_namespace(app)
    assert ns["app"] is app
    assert "config" in ns
    assert "run" in ns
    assert "Loupe" in BANNER


def test_start_loupe_ipython_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _minimal_app(tmp_path, monkeypatch)
    app.load_environment()
    app.load_configuration()
    called: list[bool] = []

    with patch(
        "almasix.console.repl._start_ipython", side_effect=lambda ns: called.append(True) or 0
    ):
        assert start_loupe(app) == 0
    assert called


def test_start_ipython_real_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Drive `_start_ipython` with a fake InteractiveShellEmbed."""
    from almasix.console import repl as repl_mod

    app = _minimal_app(tmp_path, monkeypatch)
    app.load_environment()
    app.load_configuration()
    ns = build_namespace(app)
    called: list[Any] = []

    class FakeEmbed:
        @classmethod
        def instance(cls, **kwargs):
            return cls()

        def __call__(self, using=None):
            called.append(using or "default")

    class FakeConfig:
        def __init__(self):
            self.InteractiveShellEmbed = SimpleNamespace()
            self.InteractiveShell = SimpleNamespace()
            self.TerminalInteractiveShell = SimpleNamespace()

    class FakeDisplayHook:
        def __init__(self, *a, **k):
            pass

        def __call__(self, result=None):
            return None

    with (
        patch.object(repl_mod, "_loupe_prompts_class", return_value=object),
        patch.dict(
            "sys.modules",
            {
                "IPython.terminal.embed": SimpleNamespace(InteractiveShellEmbed=FakeEmbed),
                "IPython.core.displayhook": SimpleNamespace(DisplayHook=FakeDisplayHook),
                "traitlets.config": SimpleNamespace(Config=FakeConfig),
            },
        ),
    ):
        assert repl_mod._start_ipython(ns) == 0
    assert called


def test_start_ipython_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from almasix.console import repl as repl_mod

    real_import = __import__

    def guarded(name, *args, **kwargs):
        if name.startswith("IPython") or name == "traitlets.config":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=guarded):
        assert repl_mod._start_ipython({}) is None


def test_start_ptpython_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from almasix.console import repl as repl_mod

    configured: list[bool] = []
    embeds: list[dict] = []

    class FakeRepl:
        show_signature = False
        show_docstring = False
        highlight_matching_parenthesis = False
        color_depth = ""
        enable_syntax_highlighting = False
        prompt_style = ""
        show_line_numbers = True

        def use_code_colorscheme(self, name):
            configured.append(True)

    def fake_embed(*, globals, locals, configure, title):
        configure(FakeRepl())
        embeds.append(globals)

    with patch.dict(
        "sys.modules",
        {"ptpython.repl": SimpleNamespace(embed=fake_embed)},
    ):
        assert repl_mod._start_ptpython({"x": 1}) == 0
    assert embeds and configured


def test_start_ptpython_missing() -> None:
    from almasix.console import repl as repl_mod

    real_import = __import__

    def guarded(name, *args, **kwargs):
        if name.startswith("ptpython"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=guarded):
        assert repl_mod._start_ptpython({}) is None


def test_start_rich_and_plain_consoles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from almasix.console import repl as repl_mod

    app = _minimal_app(tmp_path, monkeypatch)
    app.load_environment()
    app.load_configuration()
    ns = build_namespace(app)

    monkeypatch.setattr("builtins.input", lambda *a, **k: (_ for _ in ()).throw(EOFError()))

    assert repl_mod._start_rich_console(ns) == 0
    assert repl_mod._start_plain_console(ns) == 0

    # Rich missing → plain
    real_import = __import__

    def guarded(name, *args, **kwargs):
        if name.startswith("rich"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=guarded):
        assert repl_mod._start_rich_console(ns) == 0


def test_start_loupe_chains_to_rich(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _minimal_app(tmp_path, monkeypatch)
    app.load_environment()
    app.load_configuration()
    monkeypatch.setattr("builtins.input", lambda *a, **k: (_ for _ in ()).throw(EOFError()))
    with (
        patch("almasix.console.repl._start_ipython", return_value=None),
        patch("almasix.console.repl._start_ptpython", return_value=None),
    ):
        assert start_loupe(app) == 0


def test_start_loupe_ptpython_chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _minimal_app(tmp_path, monkeypatch)
    app.load_environment()
    app.load_configuration()
    with (
        patch("almasix.console.repl._start_ipython", return_value=None),
        patch("almasix.console.repl._start_ptpython", return_value=0),
    ):
        assert start_loupe(app) == 0


def test_loupe_prompts_tokens() -> None:
    from almasix.console.repl import _loupe_prompts_class

    prompts_cls = _loupe_prompts_class()
    shell = SimpleNamespace(execution_count=3)
    prompts = prompts_cls(shell)
    assert any("loupe" in str(t[1]) for t in prompts.in_prompt_tokens())
    assert any("out" in str(t[1]) for t in prompts.out_prompt_tokens())


def test_configure_ptpython() -> None:
    from almasix.console.repl import _configure_ptpython

    repl = SimpleNamespace(
        show_signature=False,
        show_docstring=False,
        highlight_matching_parenthesis=False,
        color_depth="",
        enable_syntax_highlighting=False,
        prompt_style="",
        show_line_numbers=True,
        use_code_colorscheme=lambda name: None,
    )
    _configure_ptpython(repl)
    assert repl.enable_syntax_highlighting is True
    assert repl.prompt_style == "ipython"


def test_rich_displayhook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from almasix.console import repl as repl_mod

    app = _minimal_app(tmp_path, monkeypatch)
    app.load_environment()
    app.load_configuration()
    ns = build_namespace(app)
    monkeypatch.setattr("builtins.input", lambda *a, **k: (_ for _ in ()).throw(EOFError()))

    # Capture displayhook by invoking rich console and calling the installed hook
    hooks: list[Any] = []

    original = sys.displayhook

    def watch(value):
        hooks.append(value)
        return original(value) if False else None

    # Let _start_rich_console install its hook, then call it
    assert repl_mod._start_rich_console(ns) == 0
    # displayhook was set during start; call it for coverage of Pretty path
    import builtins

    if sys.displayhook is not original:
        sys.displayhook(None)
        sys.displayhook({"hello": "loupe"})
        assert builtins._ == {"hello": "loupe"}


def test_build_namespace_import_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _minimal_app(tmp_path, monkeypatch)
    app.load_environment()
    app.load_configuration()

    real_import = __import__

    def guarded(name, *args, **kwargs):
        if name in {"almasix.routing", "almasix.orm", "almasix.log", "app.models.user"}:
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=guarded):
        ns = build_namespace(app)
    assert "app" in ns
    assert "Route" not in ns
    assert "DB" not in ns
    assert "log" not in ns
    assert "User" not in ns
