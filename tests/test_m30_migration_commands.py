"""M30 — ``migrate:install``, ``migrate:reset``, and ``migrate:refresh``.

The three migration commands Laravel has and Smith was missing. Each one is
driven through the kernel, the way ``smith`` reaches it, so the argv parsing
and the confirmation guard are exercised alongside the migrator.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from almasix.cache.helpers import set_manager as set_cache_manager
from almasix.console.kernel import ConsoleKernel
from almasix.console.output import Output
from almasix.orm.migration import Migrator
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


def write_migration(
    root: Path,
    stamp: str,
    table: str,
    *,
    into: str = "database/migrations",
) -> str:
    """Write a create/drop migration for ``table``, returning its migration name."""
    directory = root / into
    directory.mkdir(parents=True, exist_ok=True)
    name = f"{stamp}_create_{table}_table"
    (directory / f"{name}.py").write_text(
        "from almasix.orm import Migration, Schema\n"
        f"class Create{table.capitalize()}Table(Migration):\n"
        "    async def up(self):\n"
        f"        await Schema.create('{table}', lambda t: (t.id(), t.string('name')))\n"
        "    async def down(self):\n"
        f"        await Schema.drop_if_exists('{table}')\n",
        encoding="utf-8",
    )
    return name


def write_seeder(root: Path) -> None:
    directory = root / "database" / "seeders"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "database_seeder.py").write_text(
        "from almasix.orm import Seeder\n"
        "class DatabaseSeeder(Seeder):\n"
        "    async def run(self):\n"
        "        pass\n",
        encoding="utf-8",
    )


def apply_migrations(directory: Path) -> list[str]:
    """Apply the migrations in ``directory``, for the paths ``migrate`` cannot reach."""
    return asyncio.run(Migrator(directory).run())


def table_names() -> list[str]:
    return asyncio.run(Schema.table_names())


def has_table(name: str) -> bool:
    return asyncio.run(Schema.has_table(name))


@pytest.fixture
def build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Build]:
    def make(*, environment: str = "local") -> ConsoleKernel:
        write_app(tmp_path, environment=environment)
        monkeypatch.chdir(tmp_path)
        return ConsoleKernel.from_cwd(tmp_path)

    yield make
    set_cache_manager(None)


# --- migrate:install ---------------------------------------------------


def test_install_creates_the_migration_repository_table(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("migrate:install", []) == 0

    assert "Migration table created successfully." in capsys.readouterr().out
    assert has_table("migrations")


def test_install_says_the_repository_table_is_already_there(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    """Laravel fails a second install; Almasix reports it and succeeds."""
    kernel = build()
    assert kernel.run_argv("migrate:install", []) == 0
    capsys.readouterr()

    assert kernel.run_argv("migrate:install", []) == 0
    assert "Migration table already exists." in capsys.readouterr().out


def test_install_creates_the_table_on_the_connection_it_was_pointed_at(build: Build) -> None:
    kernel = build()

    assert kernel.run_argv("migrate:install", ["--database", "sqlite"]) == 0
    assert has_table("migrations")


def test_install_reports_a_database_it_cannot_reach(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("migrate:install", ["--database", "ghost"]) == 1
    assert "ghost" in capsys.readouterr().err


def test_install_says_which_database_name_it_could_not_read(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("migrate:install", ["--database"]) == 2
    assert "Invalid value for '--database'" in capsys.readouterr().err


# --- migrate:reset -----------------------------------------------------


def test_reset_rolls_back_every_migration_newest_first(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    older = write_migration(tmp_path, "2020_01_01_000000", "posts")
    newer = write_migration(tmp_path, "2020_01_02_000000", "tags")
    assert kernel.run_argv("migrate", []) == 0
    capsys.readouterr()

    assert kernel.run_argv("migrate:reset", ["--force"]) == 0

    out = capsys.readouterr().out
    assert out.index(newer) < out.index(older)
    assert "Rolled back 2 migration(s)." in out
    assert table_names() == ["migrations"]


def test_reset_says_when_there_is_nothing_to_roll_back(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    write_migration(tmp_path, "2020_01_01_000000", "posts")

    assert kernel.run_argv("migrate:reset", ["--force"]) == 0
    assert "Nothing to roll back." in capsys.readouterr().out


def test_reset_asks_first_and_leaves_the_migrations_alone_when_refused(
    build: Build,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    kernel = build()
    write_migration(tmp_path, "2020_01_01_000000", "posts")
    assert kernel.run_argv("migrate", []) == 0
    monkeypatch.setattr(Output, "confirm", lambda *a, **k: False)
    capsys.readouterr()

    assert kernel.run_argv("migrate:reset", []) == 1

    out = capsys.readouterr().out
    assert "This rolls back every migration that has run." in out
    assert "Nothing was changed." in out
    assert has_table("posts")


def test_reset_rolls_back_once_the_confirmation_is_given(
    build: Build, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kernel = build()
    write_migration(tmp_path, "2020_01_01_000000", "posts")
    assert kernel.run_argv("migrate", []) == 0
    monkeypatch.setattr(Output, "confirm", lambda *a, **k: True)

    assert kernel.run_argv("migrate:reset", []) == 0
    assert not has_table("posts")


def test_reset_will_not_touch_production_without_force(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build(environment="production")
    write_migration(tmp_path, "2020_01_01_000000", "posts")
    assert kernel.run_argv("migrate", []) == 0

    assert kernel.run_argv("migrate:reset", []) == 1

    assert "Application is in production (production)." in capsys.readouterr().err
    assert has_table("posts")


def test_reset_reads_the_migrations_from_the_path_it_was_given(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A relative ``--path`` is read from the working directory, as Laravel reads it."""
    kernel = build()
    name = write_migration(tmp_path, "2020_01_01_000000", "posts", into="database/extra")
    assert apply_migrations(tmp_path / "database" / "extra") == [name]
    capsys.readouterr()

    assert kernel.run_argv("migrate:reset", ["--path", "database/extra", "--force"]) == 0

    assert f"Rolled back: {name}" in capsys.readouterr().out
    assert not has_table("posts")


def test_reset_says_which_path_it_could_not_read(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("migrate:reset", ["--path", "--force"]) == 2
    assert "Invalid value for '--path'" in capsys.readouterr().err


def test_reset_reports_a_database_it_cannot_reach(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("migrate:reset", ["--database", "ghost", "--force"]) == 1
    assert "ghost" in capsys.readouterr().err


# --- migrate:refresh ---------------------------------------------------


def test_refresh_rolls_everything_back_and_runs_it_again(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    name = write_migration(tmp_path, "2020_01_01_000000", "posts")
    assert kernel.run_argv("migrate", []) == 0
    capsys.readouterr()

    assert kernel.run_argv("migrate:refresh", ["--force"]) == 0

    out = capsys.readouterr().out
    assert f"Rolled back: {name}" in out
    assert f"Migrated: {name}" in out
    assert has_table("posts")


def test_refresh_with_a_step_count_only_re_runs_that_many_batches(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    older = write_migration(tmp_path, "2020_01_01_000000", "posts")
    assert kernel.run_argv("migrate", []) == 0
    newer = write_migration(tmp_path, "2020_01_02_000000", "tags")
    assert kernel.run_argv("migrate", []) == 0
    capsys.readouterr()

    assert kernel.run_argv("migrate:refresh", ["--step", "1", "--force"]) == 0

    out = capsys.readouterr().out
    assert f"Rolled back: {newer}" in out
    assert f"Migrated: {newer}" in out
    assert older not in out
    assert has_table("posts")
    assert has_table("tags")


def test_refresh_says_when_there_is_nothing_to_migrate(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("migrate:refresh", ["--force"]) == 0
    assert "Nothing to migrate." in capsys.readouterr().out


def test_refresh_seeds_the_database_when_asked(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    write_migration(tmp_path, "2020_01_01_000000", "posts")
    write_seeder(tmp_path)

    assert kernel.run_argv("migrate:refresh", ["--seed", "--force"]) == 0
    assert "Database seeding completed successfully." in capsys.readouterr().out


def test_refresh_says_which_step_count_it_could_not_read(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("migrate:refresh", ["--step", "some", "--force"]) == 2
    assert "not a valid integer" in capsys.readouterr().err


def test_refresh_refuses_a_step_count_below_zero(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    """``rollback`` floors its step at one, so a negative would quietly mean one."""
    kernel = build()

    assert kernel.run_argv("migrate:refresh", ["--step=-2", "--force"]) == 2
    assert "not a number of batches" in capsys.readouterr().err


def test_refresh_says_which_database_name_it_could_not_read(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("migrate:refresh", ["--database", "--force"]) == 2
    assert "Invalid value for '--database'" in capsys.readouterr().err


def test_refresh_asks_first_and_leaves_the_migrations_alone_when_refused(
    build: Build,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    kernel = build()
    write_migration(tmp_path, "2020_01_01_000000", "posts")
    assert kernel.run_argv("migrate", []) == 0
    monkeypatch.setattr(Output, "confirm", lambda *a, **k: False)
    capsys.readouterr()

    assert kernel.run_argv("migrate:refresh", []) == 1

    assert "This rolls back and re-runs every migration." in capsys.readouterr().out
    assert has_table("posts")


def test_refresh_says_how_many_batches_it_is_about_to_re_run(
    build: Build, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    monkeypatch.setattr(Output, "confirm", lambda *a, **k: False)

    assert kernel.run_argv("migrate:refresh", ["--step", "2"]) == 1

    assert "the last 2 batch(es) of migrations" in capsys.readouterr().out


def test_refresh_reports_a_database_it_cannot_reach(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("migrate:refresh", ["--database", "ghost", "--force"]) == 1
    assert "ghost" in capsys.readouterr().err
