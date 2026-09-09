"""M30 smoke — Smith-shaped console surface in the living example."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from almasix.console.facade import Smith
from almasix.console.kernel import ConsoleKernel
from almasix.smith.cli import app as smith_app
from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke, pytest.mark.regression]

PROGRESS = Path(__file__).resolve().parents[2] / "examples" / "progress"
runner = CliRunner()


@pytest.fixture()
def progress_kernel(monkeypatch: pytest.MonkeyPatch) -> ConsoleKernel:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    kernel = ConsoleKernel.from_cwd(PROGRESS)
    kernel.load_console_routes()
    kernel.register_on_typer(smith_app)
    yield kernel
    Smith.set_kernel(None)


def test_signature_shortcuts_arrays_and_output(progress_kernel: ConsoleKernel) -> None:
    result = runner.invoke(smith_app, ["progress:console", "daily", "-T", "alpha", "-T", "beta"])
    assert result.exit_code == 0, result.stdout
    assert "Building daily" in result.stdout
    assert "alpha, beta" in result.stdout
    assert "steps -> [10, 20, 30]" in result.stdout
    # progress:console calls progress:hello silently and echoes its output.
    assert "console kernel is alive" in result.stdout


def test_closure_command_from_routes_console(progress_kernel: ConsoleKernel) -> None:
    assert "progress:greet" in progress_kernel.commands
    assert progress_kernel.commands["progress:greet"].description.startswith("M30 living example")
    result = runner.invoke(smith_app, ["progress:greet", "ada", "--loud"])
    assert result.exit_code == 0, result.stdout
    assert "HELLO FROM ROUTES/CONSOLE.PY, ADA" in result.stdout


def test_isolatable_command_takes_and_releases_its_lock(progress_kernel: ConsoleKernel) -> None:
    from almasix.console import isolation

    assert progress_kernel.run_argv("progress:import", ["--isolated"]) == 0

    held = isolation.acquire("progress:import", 60, PROGRESS)
    assert held is not None
    assert progress_kernel.run_argv("progress:import", ["--isolated"]) == 0
    assert progress_kernel.run_argv("progress:import", ["--isolated=12"]) == 12
    held.release()


def test_smith_call_reaches_example_commands(progress_kernel: ConsoleKernel) -> None:
    assert Smith.call_silently("progress:hello", {"name": "Smith"}) == 0
    assert "Hello, Smith" in Smith.output()
    assert Smith.has("progress:console") is True


PAGE = Path(__file__).resolve().parents[2] / "website" / "src" / "content" / "docs" / "console.md"

#: Laravel Artisan doc order, mapped onto Almasix headings (first section is Smith).
LARAVEL_ARTISAN_DOC_ORDER = [
    "Smith",
    "Loupe REPL",
    "Writing commands",
    "Closure commands",
    "Isolatable commands",
    "Defining input expectations",
    "Command I/O",
    "Registering commands",
    "Programmatically executing commands",
    "Signal handling",
    "Stub customization",
    "Publishing package files",
    "Events",
]


def page_sections() -> list[str]:
    """Top-level headings, ignoring any that a fenced code block contains."""
    sections: list[str] = []
    fenced = False
    for line in PAGE.read_text(encoding="utf-8").split("\n"):
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("## "):
            sections.append(line[3:].strip())
    return sections


def documented_commands() -> set[str]:
    reference = PAGE.read_text(encoding="utf-8")
    reference = reference[reference.index("## Command reference") :]
    return set(re.findall(r"^\| `([a-z][a-z0-9:_-]*)` \|", reference, re.M))


def framework_commands() -> dict[str, type]:
    kernel = ConsoleKernel.for_cwd()
    kernel.discover_framework_commands()
    return {cls.name(): cls for cls in kernel.commands.values()}


def test_the_page_follows_laravels_artisan_doc_order() -> None:
    """Someone reading both pages side by side should not have to hunt."""
    sections = page_sections()

    assert [
        name for name in sections if name in LARAVEL_ARTISAN_DOC_ORDER
    ] == LARAVEL_ARTISAN_DOC_ORDER


def test_every_command_the_framework_ships_is_in_the_reference() -> None:
    """A new command must bring its row, or the reference quietly goes stale."""
    assert set(framework_commands()) - documented_commands() == set()


def test_the_reference_documents_nothing_that_does_not_exist() -> None:
    commands = framework_commands()
    aliases = {alias for cls in commands.values() for alias in cls.aliases}

    assert documented_commands() - set(commands) - aliases == set()


def test_the_reference_describes_each_command_the_way_the_command_does() -> None:
    """The descriptions are the commands' own, so `smith list` and the page agree."""
    page = PAGE.read_text(encoding="utf-8")
    page = page[page.index("## Command reference") :]

    for name, command in sorted(framework_commands().items()):
        assert f"| `{name}` | {command.description}" in page, name
