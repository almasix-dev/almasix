"""M30 smoke — Artisan-shaped console surface in the living example."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from avalon.console.facade import Artisan
from avalon.console.kernel import ConsoleKernel
from avalon.grail.cli import app as grail_app
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
    kernel.register_on_typer(grail_app)
    yield kernel
    Artisan.set_kernel(None)


def test_signature_shortcuts_arrays_and_output(progress_kernel: ConsoleKernel) -> None:
    result = runner.invoke(grail_app, ["progress:console", "daily", "-T", "alpha", "-T", "beta"])
    assert result.exit_code == 0, result.stdout
    assert "Building daily" in result.stdout
    assert "alpha, beta" in result.stdout
    assert "steps -> [10, 20, 30]" in result.stdout
    # progress:console calls progress:hello silently and echoes its output.
    assert "console kernel is alive" in result.stdout


def test_closure_command_from_routes_console(progress_kernel: ConsoleKernel) -> None:
    assert "progress:greet" in progress_kernel.commands
    assert progress_kernel.commands["progress:greet"].description.startswith("M30 living example")
    result = runner.invoke(grail_app, ["progress:greet", "ada", "--loud"])
    assert result.exit_code == 0, result.stdout
    assert "HELLO FROM ROUTES/CONSOLE.PY, ADA" in result.stdout


def test_isolatable_command_takes_and_releases_its_lock(progress_kernel: ConsoleKernel) -> None:
    from avalon.console import isolation

    assert progress_kernel.run_argv("progress:import", ["--isolated"]) == 0

    held = isolation.acquire("progress:import", 60, PROGRESS)
    assert held is not None
    assert progress_kernel.run_argv("progress:import", ["--isolated"]) == 0
    assert progress_kernel.run_argv("progress:import", ["--isolated=12"]) == 12
    held.release()


def test_artisan_call_reaches_example_commands(progress_kernel: ConsoleKernel) -> None:
    assert Artisan.call_silently("progress:hello", {"name": "Grail"}) == 0
    assert "Hello, Grail" in Artisan.output()
    assert Artisan.has("progress:console") is True
