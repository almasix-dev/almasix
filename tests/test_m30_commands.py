"""M30 — the migrated commands, where the argv parser hands over a string.

Typer used to coerce and validate option types at the door. Almasix's parser
hands every option over as text, so each command owns the conversion — and the
error when it fails.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from almasix.console.kernel import ConsoleKernel


@pytest.fixture()
def kernel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ConsoleKernel:
    monkeypatch.chdir(tmp_path)
    built = ConsoleKernel.for_cwd(tmp_path)
    built.discover_framework_commands()
    return built


def test_serve_says_which_port_it_could_not_read(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    code = kernel.run_argv("serve", ["--app", "x:y", "--port", "three thousand"])

    assert code == 2  # Command.INVALID
    assert "not a valid integer" in capsys.readouterr().err


def test_the_schedule_worker_says_which_sleep_it_could_not_read(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    code = kernel.run_argv("schedule:work", ["--sleep", "soon"])

    assert code == 2
    assert "not a valid integer" in capsys.readouterr().err


def test_lang_missing_asks_for_the_locale_it_needs(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    """Almasix's signature language has no required option, so the command checks."""
    code = kernel.run_argv("lang:missing", [])

    assert code == 1
    assert "--locale" in capsys.readouterr().err


def test_migrate_reports_a_database_it_cannot_reach(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from almasix.console.commands.database import DatabaseCommand

    async def explode(**_: object) -> None:
        raise RuntimeError("no such table: migrations")

    monkeypatch.setattr(
        DatabaseCommand,
        "migrator",
        lambda self, *args: type("Broken", (), {"run": staticmethod(explode)})(),
    )
    kernel.boot_application()

    assert kernel.run_argv("migrate", []) == 1
    assert "no such table" in capsys.readouterr().err
