"""M30 — one command surface: discovery, aliases, lazy boot, and signature help.

Smith used to have two consoles: hand-written Typer callbacks and discovered
``Command`` classes. These tests hold the line that there is only one.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from almasix.console.command import Command
from almasix.console.front_door import FrontDoor, install, report_failures
from almasix.console.help import arguments_of, help_text, metavar, options_of, usage
from almasix.console.kernel import ConsoleKernel
from almasix.installer.scaffold import scaffold_app

runner = CliRunner()

BROKEN = """
from almasix.console.command import Command
from almasix.nowhere import Missing  # noqa
"""

WORKS = """
from almasix.console.command import Command


class WorksCommand(Command):
    signature = "probe:works"
    description = "Proves discovery kept going"

    def handle(self) -> int:
        self.line("still here")
        return 0
"""


@pytest.fixture()
def app_root(tmp_path: Path) -> Path:
    return scaffold_app("probeapp", destination=tmp_path / "probeapp")


def test_a_broken_command_module_does_not_hide_its_siblings(app_root: Path) -> None:
    commands = app_root / "app" / "console" / "commands"
    (commands / "broken.py").write_text(BROKEN, encoding="utf-8")
    (commands / "works.py").write_text(WORKS, encoding="utf-8")

    kernel = ConsoleKernel.from_cwd(app_root)

    assert "probe:works" in kernel.commands
    assert [failure.module for failure in kernel.failures] == ["app.console.commands.broken"]
    assert "No module named 'almasix.nowhere'" in kernel.failures[0].summary()


def test_the_broken_module_is_named_on_every_run_not_only_on_list(
    app_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (app_root / "app" / "console" / "commands" / "broken.py").write_text(BROKEN, encoding="utf-8")

    kernel = ConsoleKernel.from_cwd(app_root)
    report_failures(kernel)

    assert "Command not loaded — app.console.commands.broken" in capsys.readouterr().err


def test_a_directory_of_commands_loads_without_an_init_file(app_root: Path) -> None:
    commands = app_root / "app" / "console" / "commands"
    (commands / "__init__.py").unlink()
    (commands / "works.py").write_text(WORKS, encoding="utf-8")

    kernel = ConsoleKernel.from_cwd(app_root)

    assert "probe:works" in kernel.commands


def test_the_directory_loader_keeps_the_files_it_can_read(tmp_path: Path) -> None:
    """The fallback for when ``app.console.commands`` will not import at all.

    It loads each file under a synthetic module name, so it survives a stale or
    foreign ``app`` in ``sys.modules`` — and a file that raises costs only
    itself.
    """
    import sys

    commands = tmp_path / "commands"
    commands.mkdir()
    (commands / "works.py").write_text(WORKS, encoding="utf-8")
    (commands / "broken.py").write_text(BROKEN, encoding="utf-8")
    (commands / "_ignored.py").write_text("raise RuntimeError('never read')\n", encoding="utf-8")

    kernel = ConsoleKernel.for_cwd(tmp_path)
    kernel._load_path(commands)

    assert "probe:works" in kernel.commands
    assert [Path(failure.module).name for failure in kernel.failures] == ["broken.py"]
    assert not [name for name in sys.modules if "almasix_app_command_broken" in name]


def test_a_broken_file_is_reported_once_not_once_per_scan(app_root: Path) -> None:
    (app_root / "app" / "console" / "commands" / "broken.py").write_text(BROKEN, encoding="utf-8")

    kernel = ConsoleKernel.from_cwd(app_root)

    assert len(kernel.failures) == 1


class AliasedCommand(Command):
    signature = "probe:aliased"
    description = "A command with other names"
    aliases = ("probe:other", "probe:third")

    def handle(self) -> int:
        self.line("aliased")
        return 0


def test_aliases_answer_to_the_same_command(tmp_path: Path) -> None:
    kernel = ConsoleKernel.for_cwd(tmp_path)
    kernel.register(AliasedCommand)

    assert kernel.commands["probe:other"] is AliasedCommand
    assert kernel.commands["probe:third"] is AliasedCommand
    assert kernel.run_argv("probe:other", []) == 0


def test_generators_run_without_an_application(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bare directory has no config, so a generator must not want one."""
    monkeypatch.chdir(tmp_path)
    kernel = ConsoleKernel.for_cwd(tmp_path)
    kernel.discover_framework_commands()

    assert kernel.commands["make:controller"].boots_application is False
    assert kernel.run_argv("make:controller", ["PostController"]) == 0
    assert not kernel.app.is_bootstrapped
    assert (tmp_path / "app" / "http" / "controllers" / "post_controller.py").is_file()


class DocumentedCommand(Command):
    signature = (
        "mail:send {user : The user ID} {--Q|queue=default : Which queue} "
        "{--force : Skip the confirmation} {--cc=* : Extra recipients}"
    )
    description = "Mail one user"
    aliases = ("mail:deliver",)

    def handle(self) -> int:
        return 0


def test_the_signature_writes_its_own_help() -> None:
    assert usage(DocumentedCommand) == (
        "mail:send <user> [-Q, --queue=QUEUE] [--force] [--cc=CC...]"
    )
    assert metavar(DocumentedCommand) == "<user> [-Q, --queue=QUEUE] [--force] [--cc=CC...]"
    assert arguments_of(DocumentedCommand) == [("<user>", "The user ID")]
    assert options_of(DocumentedCommand) == [
        ("-Q, --queue=QUEUE", "Which queue [default: default]"),
        ("--force", "Skip the confirmation"),
        ("--cc=CC...", "Extra recipients"),
    ]

    body = help_text(DocumentedCommand)
    assert "Mail one user" in body
    assert "The user ID" in body
    assert "-Q, --queue=QUEUE" in body
    assert "mail:deliver" in body


def test_a_command_without_a_signature_still_has_help() -> None:
    class Bare(Command):
        description = "Nothing to declare"

        def handle(self) -> int:
            return 0

    assert help_text(Bare) == "Nothing to declare"


def test_optional_and_variadic_arguments_show_how_they_are_typed() -> None:
    class Prune(Command):
        signature = "prune {tables?} {--except=*}"
        description = "Prune"

        def handle(self) -> int:
            return 0

    class Backfill(Command):
        signature = "backfill {ids*}"
        description = "Backfill"

        def handle(self) -> int:
            return 0

    assert metavar(Prune) == "[<tables>] [--except=EXCEPT...]"
    assert metavar(Backfill) == "[<ids>...]"


def test_input_never_overwrites_the_commands_own_surface(tmp_path: Path) -> None:
    """``serve --app x:y`` must not replace the application on the command."""

    class Collider(Command):
        signature = "collide {--app=} {--kernel=}"
        description = "Options that share a name with the command's own handles"

        def handle(self) -> int:
            assert self.option("app") == "x:y"
            assert self.app is not None and hasattr(self.app, "base_path")
            assert self.kernel is not None and hasattr(self.kernel, "commands")
            return 0

    kernel = ConsoleKernel.for_cwd(tmp_path)
    kernel.register(Collider)

    assert kernel.run_argv("collide", ["--app", "x:y", "--kernel", "nope"]) == 0


def test_a_broken_command_file_is_forgotten_not_half_imported(app_root: Path) -> None:
    """The failed module must not linger in ``sys.modules`` as a shell."""
    import sys

    commands = app_root / "app" / "console" / "commands"
    (commands / "__init__.py").unlink()
    (commands / "broken.py").write_text(BROKEN, encoding="utf-8")

    before = set(sys.modules)
    kernel = ConsoleKernel.from_cwd(app_root)

    assert len(kernel.failures) == 1
    assert not [name for name in set(sys.modules) - before if "broken" in name]


def test_an_application_that_will_not_boot_is_reported_not_swallowed(
    app_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ConsoleKernel,
        "boot_application",
        lambda self: (_ for _ in ()).throw(RuntimeError("config is a mess")),
    )

    front = typer.Typer()
    kernel = install(front, cwd=app_root)

    assert [failure.module for failure in kernel.failures] == ["the application"]
    assert "config is a mess" in kernel.failures[0].summary()
    # The framework's own commands are still there to fix it with.
    assert "make:controller" in kernel.commands


def test_the_front_door_follows_the_working_directory(app_root: Path, tmp_path: Path) -> None:
    front = typer.Typer()
    door = FrontDoor(front)

    bare = door.kernel(tmp_path / "elsewhere")
    (tmp_path / "elsewhere").mkdir(exist_ok=True)
    assert door.kernel(tmp_path / "elsewhere") is bare

    (app_root / "app" / "console" / "commands" / "works.py").write_text(WORKS, encoding="utf-8")
    moved = door.kernel(app_root)

    assert moved is not bare
    assert "probe:works" in moved.commands
    assert "probe:works" in {command.name for command in front.registered_commands}


def test_the_front_door_attaches_the_framework_commands_in_a_bare_directory(
    tmp_path: Path,
) -> None:
    front = typer.Typer()
    kernel = install(front, cwd=tmp_path)
    attached = {command.name for command in front.registered_commands}

    assert "version" in attached
    assert "make:controller" in attached
    assert kernel.failures == []


def test_the_front_door_adds_the_applications_own_commands(app_root: Path) -> None:
    (app_root / "app" / "console" / "commands" / "works.py").write_text(WORKS, encoding="utf-8")

    front = typer.Typer()
    install(front, cwd=app_root)

    assert "probe:works" in {command.name for command in front.registered_commands}


def test_the_cli_module_declares_no_commands_of_its_own() -> None:
    """The M30 gate: nothing is reachable through Typer alone.

    Smith's CLI module is the front door and nothing else — a hand-written
    ``@app.command`` there would be a command that ``Artisan.call`` and the
    scheduler cannot see, which is the split M30 closed.
    """
    source = Path("src/almasix/smith/cli.py").read_text(encoding="utf-8")

    assert "@app.command" not in source
    assert "install(app)" in source


def test_what_the_front_door_offers_is_exactly_what_the_kernel_knows(app_root: Path) -> None:
    front = typer.Typer()
    kernel = install(front, cwd=app_root)

    offered = {command.name for command in front.registered_commands if command.name}
    assert offered, "the front door registered no commands"
    assert offered <= set(kernel.commands), sorted(offered - set(kernel.commands))
    for name in ("version", "make:model", "migrate", "schedule:list", "serve", "list", "loupe"):
        assert name in offered


def test_importing_a_command_module_first_does_not_hide_its_commands() -> None:
    """Discovery must not depend on what the interpreter imported first.

    ``almasix.smith`` used to import the CLI, which discovers every command
    module. A command module that imported anything from ``almasix.smith``
    therefore triggered discovery of itself, mid-import, before its classes
    existed — and ``serve`` silently vanished from the CLI for the rest of
    the process, depending only on import order.
    """
    untouched = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, almasix.smith; print('almasix.smith.cli' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
    )
    assert untouched.stdout.strip() == "False", "importing almasix.smith still builds the CLI"

    script = (
        "import almasix.console.commands.runtime\n"
        "from almasix.smith.cli import app\n"
        "names = [c.name for c in app.registered_commands]\n"
        "assert 'serve' in names, sorted(names)\n"
        "from almasix.smith import app as lazy\n"
        "assert lazy is app\n"
        "print('ok')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, cwd=Path.cwd()
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_the_lazy_smith_attribute_resolves_the_cli_and_nothing_else() -> None:
    import almasix.smith
    from almasix.smith.cli import app

    assert almasix.smith.app is app
    with pytest.raises(AttributeError, match="no attribute 'kernel'"):
        almasix.smith.kernel


CYCLE = """
from almasix.console.kernel import ConsoleKernel

# Discovery, from inside a module discovery is itself importing. The kernel
# below re-enters this very module, which Python has not finished executing —
# so the command underneath does not exist yet.
inner = ConsoleKernel.for_cwd()
inner._load_package("cyclepkg")
failures = list(inner.failures)

from almasix.console.command import Command


class CycleCommand(Command):
    signature = "probe:cycle"
"""


def test_a_module_discovered_mid_import_is_reported_not_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cycle that does slip through says so, rather than dropping commands."""
    package = tmp_path / "cyclepkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "cycle.py").write_text(CYCLE, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))

    import importlib

    module = importlib.import_module("cyclepkg.cycle")
    monkeypatch.delitem(sys.modules, "cyclepkg.cycle", raising=False)
    monkeypatch.delitem(sys.modules, "cyclepkg", raising=False)

    assert [failure.module for failure in module.failures] == ["cyclepkg.cycle"]
    assert "still importing" in module.failures[0].summary()
    # Not that it matters to the user, but the outer import did finish.
    assert module.CycleCommand.name() == "probe:cycle"


def test_no_orm_module_imports_the_console_at_module_scope() -> None:
    """Layering: the console sits above the ORM, so the ORM must not need it first.

    ``almasix.orm.migration`` imported ``almasix.console.stub`` at module scope
    to render migration stubs. Importing down from up makes the two mutually
    importing, and a command module that pulled the ORM in mid-import saw a
    half-built module — once, as a ``NameError`` on ``render`` that then took
    twenty runs to not reproduce. Inside a function the import happens after
    both modules exist, which is why this checks module scope only.
    """
    offenders: list[str] = []
    for path in sorted(Path("src/almasix/orm").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            reference = ""
            if isinstance(node, ast.ImportFrom):
                reference = node.module or ""
            elif isinstance(node, ast.Import):
                reference = node.names[0].name
            if reference.startswith("almasix.console"):
                offenders.append(f"{path.name}:{node.lineno} imports {reference}")

    assert offenders == [], offenders


def test_making_a_migration_still_renders_its_stub(tmp_path: Path) -> None:
    """The import moved into the function, so prove the function still has it."""
    from almasix.orm.migration import make_migration

    path = make_migration("create_users_table", tmp_path / "migrations")

    assert "class CreateUsersTable" in path.read_text(encoding="utf-8")
