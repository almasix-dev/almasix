"""M30 — ``db:wipe``, and the two flags it will not pretend to support."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from almasix.cache.helpers import set_manager as set_cache_manager
from almasix.console.kernel import ConsoleKernel
from almasix.console.output import Output
from almasix.orm.schema import Schema

Build = Callable[..., ConsoleKernel]


def write_app(root: Path, *, environment: str) -> None:
    """The smallest tree ``ConsoleKernel.from_cwd`` will boot as an application."""
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "bootstrap").mkdir(exist_ok=True)
    (root / "bootstrap" / "app.py").write_text("# stub\n", encoding="utf-8")
    files = {
        "app.py": (
            f'config = {{"name": "M30", "env": "{environment}", "debug": False, "providers": []}}\n'
        ),
        "logging.py": "config = {'default': 'null', 'channels': {'null': {'driver': 'null'}}}\n",
        "database.py": (
            "config = {'default': 'sqlite', 'connections': "
            "{'sqlite': {'driver': 'sqlite', 'database': ':memory:'}}}\n"
        ),
    }
    for name, body in files.items():
        (root / "config" / name).write_text(body, encoding="utf-8")


def make_tables(*names: str) -> None:
    async def build() -> None:
        for name in names:
            await Schema.create(name, lambda blueprint: blueprint.id())

    asyncio.run(build())


def table_names() -> list[str]:
    return asyncio.run(Schema.table_names())


@pytest.fixture
def build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Build]:
    def make(*, environment: str = "local") -> ConsoleKernel:
        write_app(tmp_path, environment=environment)
        monkeypatch.chdir(tmp_path)
        return ConsoleKernel.from_cwd(tmp_path)

    yield make
    set_cache_manager(None)


def test_db_wipe_drops_every_table(build: Build, capsys: pytest.CaptureFixture[str]) -> None:
    kernel = build()
    make_tables("posts", "users")

    assert kernel.run_argv("db:wipe", ["--force"]) == 0

    out = capsys.readouterr().out
    assert "Dropped: posts" in out
    assert "Dropped: users" in out
    assert "Dropped 2 table(s)." in out
    assert table_names() == []


def test_db_wipe_says_when_there_is_nothing_to_drop(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("db:wipe", ["--force"]) == 0
    assert "Nothing to drop." in capsys.readouterr().out


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["--drop-views"], "--drop-views cannot be honoured"),
        (["--drop-types"], "--drop-types cannot be honoured"),
        (["--drop-views", "--drop-types"], "--drop-views and --drop-types cannot be honoured"),
    ],
)
def test_db_wipe_refuses_views_and_types_rather_than_ignore_them(
    argv: list[str], expected: str, build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    """Almasix's schema layer knows tables only, and says so before dropping any."""
    kernel = build()
    make_tables("posts")

    assert kernel.run_argv("db:wipe", [*argv, "--force"]) == 2

    assert expected in capsys.readouterr().err
    assert table_names() == ["posts"]


def test_db_wipe_asks_first_and_leaves_the_tables_alone_when_refused(
    build: Build, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    make_tables("posts")
    monkeypatch.setattr(Output, "confirm", lambda *a, **k: False)

    assert kernel.run_argv("db:wipe", []) == 1

    out = capsys.readouterr().out
    assert "This drops every table in the [default] database." in out
    assert "Nothing was changed." in out
    assert table_names() == ["posts"]


def test_db_wipe_proceeds_once_the_confirmation_is_given(
    build: Build, monkeypatch: pytest.MonkeyPatch
) -> None:
    kernel = build()
    make_tables("posts")
    monkeypatch.setattr(Output, "confirm", lambda *a, **k: True)

    assert kernel.run_argv("db:wipe", []) == 0
    assert table_names() == []


def test_db_wipe_will_not_touch_production_without_force(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build(environment="production")
    make_tables("posts")

    assert kernel.run_argv("db:wipe", []) == 1

    assert "Application is in production (production)." in capsys.readouterr().err
    assert table_names() == ["posts"]


def test_db_wipe_wipes_production_when_forced(build: Build) -> None:
    kernel = build(environment="production")
    make_tables("posts")

    assert kernel.run_argv("db:wipe", ["--force"]) == 0
    assert table_names() == []


def test_db_wipe_names_the_connection_it_was_pointed_at(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    make_tables("posts")

    assert kernel.run_argv("db:wipe", ["--database", "sqlite", "--force"]) == 0
    assert "Dropped 1 table(s)." in capsys.readouterr().out


def test_db_wipe_reports_a_connection_it_cannot_reach(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    make_tables("posts")

    assert kernel.run_argv("db:wipe", ["--database", "ghost", "--force"]) == 1

    assert "ghost" in capsys.readouterr().err
    assert table_names() == ["posts"]


def test_db_wipe_says_which_database_name_it_could_not_read(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("db:wipe", ["--database", "--force"]) == 2
    assert "Invalid value for '--database'" in capsys.readouterr().err


def test_db_wipe_can_be_called_in_process(build: Build, capsys: pytest.CaptureFixture[str]) -> None:
    """``Artisan.call`` passes no options, so every flag has to be optional."""
    kernel = build()
    make_tables("posts")
    options: dict[str, Any] = {"force": True}

    assert kernel.run_command("db:wipe", options=options) == 0
    assert "Dropped 1 table(s)." in capsys.readouterr().out
