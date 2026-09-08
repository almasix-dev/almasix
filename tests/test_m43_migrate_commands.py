"""The migrate commands with the flags Laravel gives them."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_m30_migration_commands import (  # noqa: F401
    Build,
    build,
    has_table,
    table_names,
    write_migration,
)


def test_migrate_pretends_instead_of_running(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    write_migration(tmp_path, "2020_01_01_000000", "posts")

    assert kernel.run_argv("migrate", ["--pretend"]) == 0

    printed = capsys.readouterr().out
    assert "CREATE TABLE posts" in printed
    assert not has_table("posts")


def test_migrate_gives_each_migration_its_own_batch_when_asked(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    write_migration(tmp_path, "2020_01_01_000000", "posts")
    write_migration(tmp_path, "2020_01_02_000000", "tags")

    assert kernel.run_argv("migrate", ["--step"]) == 0
    capsys.readouterr()

    assert kernel.run_argv("migrate:rollback", []) == 0
    assert "create_tags_table" in capsys.readouterr().out
    assert has_table("posts")


def test_migrate_reads_the_path_it_is_given(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    write_migration(tmp_path, "2020_01_01_000000", "posts", into="database/extra")

    assert kernel.run_argv("migrate", ["--path", "database/extra"]) == 0
    assert has_table("posts")
    assert "Migrated:" in capsys.readouterr().out


def test_migrate_reads_several_paths_at_once(build: Build, tmp_path: Path) -> None:
    kernel = build()
    write_migration(tmp_path, "2020_01_01_000000", "posts", into="database/one")
    write_migration(tmp_path, "2020_01_02_000000", "tags", into="database/two")

    assert kernel.run_argv("migrate", ["--path", "database/one,database/two"]) == 0
    assert has_table("posts") and has_table("tags")


def test_migrate_reports_the_options_it_cannot_read(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("migrate", ["--database"]) == 2
    assert "--database" in capsys.readouterr().err
    assert kernel.run_argv("migrate", ["--path"]) == 2
    assert "--path" in capsys.readouterr().err


def test_migrate_stops_at_a_production_database_without_force(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build(environment="production")
    write_migration(tmp_path, "2020_01_01_000000", "posts")

    assert kernel.run_argv("migrate", []) == 1
    assert "production" in capsys.readouterr().err
    assert not has_table("posts")

    assert kernel.run_argv("migrate", ["--force"]) == 0
    assert has_table("posts")


def test_a_graceful_migrate_reports_a_failure_as_success(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """For a deploy pipeline that must not stop on a database that is not there."""
    kernel = build()
    directory = tmp_path / "database" / "migrations"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "2020_01_01_000000_broken.py").write_text(
        "from almasix.orm import Migration\n"
        "class Broken(Migration):\n"
        "    async def up(self):\n"
        "        raise RuntimeError('the database is not there')\n"
        "    async def down(self):\n"
        "        pass\n",
        encoding="utf-8",
    )

    assert kernel.run_argv("migrate", []) == 1
    capsys.readouterr()
    assert kernel.run_argv("migrate", ["--graceful"]) == 0


def test_rollback_counts_migrations_and_can_name_a_batch(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    write_migration(tmp_path, "2020_01_01_000000", "posts")
    write_migration(tmp_path, "2020_01_02_000000", "tags")
    assert kernel.run_argv("migrate", []) == 0
    capsys.readouterr()

    assert kernel.run_argv("migrate:rollback", ["--step", "1"]) == 0
    assert "create_tags_table" in capsys.readouterr().out
    assert has_table("posts") and not has_table("tags")

    assert kernel.run_argv("migrate:rollback", ["--batch", "1"]) == 0
    assert not has_table("posts")

    assert kernel.run_argv("migrate:rollback", []) == 0
    assert "Nothing to roll back." in capsys.readouterr().out


def test_rollback_says_which_count_it_could_not_read(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("migrate:rollback", ["--step", "soon"]) == 2
    assert "not a valid integer" in capsys.readouterr().err
    assert kernel.run_argv("migrate:rollback", ["--batch=-2"]) == 2
    assert "not a count" in capsys.readouterr().err


def test_rollback_stops_at_a_production_database_and_bad_options(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build(environment="production")
    write_migration(tmp_path, "2020_01_01_000000", "posts")
    assert kernel.run_argv("migrate", ["--force"]) == 0
    capsys.readouterr()

    assert kernel.run_argv("migrate:rollback", []) == 1
    assert "production" in capsys.readouterr().err
    assert has_table("posts")

    assert kernel.run_argv("migrate:rollback", ["--database"]) == 2
    assert "--database" in capsys.readouterr().err


def test_a_schema_path_may_be_absolute(build: Build, tmp_path: Path) -> None:
    kernel = build()
    write_migration(tmp_path, "2020_01_01_000000", "posts")
    assert kernel.run_argv("migrate", []) == 0
    assert kernel.run_argv("schema:dump", []) == 0

    dump = tmp_path / "database" / "schema" / "database-schema.sql"
    kernel = build()
    assert kernel.run_argv("migrate", ["--schema-path", str(dump)]) == 0
    assert has_table("posts")


def test_rollback_can_pretend_too(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    write_migration(tmp_path, "2020_01_01_000000", "posts")
    assert kernel.run_argv("migrate", []) == 0
    capsys.readouterr()

    assert kernel.run_argv("migrate:rollback", ["--pretend"]) == 0
    assert "DROP TABLE" in capsys.readouterr().out
    assert has_table("posts")


def test_status_shows_the_batch_and_can_hide_what_has_run(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    write_migration(tmp_path, "2020_01_01_000000", "posts")
    assert kernel.run_argv("migrate", []) == 0
    write_migration(tmp_path, "2020_01_02_000000", "tags")
    capsys.readouterr()

    assert kernel.run_argv("migrate:status", []) == 0
    printed = capsys.readouterr().out
    assert "Ran [1]" in printed
    assert "Pending" in printed

    assert kernel.run_argv("migrate:status", ["--pending"]) == 0
    printed = capsys.readouterr().out
    assert "create_tags_table" in printed
    assert "create_posts_table" not in printed


def test_status_says_when_nothing_is_pending(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    write_migration(tmp_path, "2020_01_01_000000", "posts")
    assert kernel.run_argv("migrate", []) == 0
    capsys.readouterr()

    assert kernel.run_argv("migrate:status", ["--pending"]) == 0
    assert "No pending migrations." in capsys.readouterr().out


def test_status_reports_the_options_it_cannot_read(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    assert kernel.run_argv("migrate:status", ["--database"]) == 2
    assert "--database" in capsys.readouterr().err


def test_fresh_takes_the_flags_the_other_commands_take(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    write_migration(tmp_path, "2020_01_01_000000", "posts", into="database/extra")

    assert kernel.run_argv("migrate", ["--path", "database/extra"]) == 0
    capsys.readouterr()

    assert kernel.run_argv("migrate:fresh", ["--path", "database/extra", "--step"]) == 0
    assert "Migrated:" in capsys.readouterr().out
    assert has_table("posts")

    assert kernel.run_argv("migrate:fresh", ["--database"]) == 2


def test_fresh_stops_at_a_production_database(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build(environment="production")
    write_migration(tmp_path, "2020_01_01_000000", "posts")

    assert kernel.run_argv("migrate:fresh", []) == 1
    assert "production" in capsys.readouterr().err


def test_a_dump_lets_a_fresh_database_skip_the_migrations_behind_it(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    write_migration(tmp_path, "2020_01_01_000000", "posts")
    assert kernel.run_argv("migrate", []) == 0
    capsys.readouterr()

    assert kernel.run_argv("schema:dump", []) == 0
    dump = tmp_path / "database" / "schema" / "database-schema.sql"
    assert dump.is_file()
    assert "Database schema dumped" in capsys.readouterr().out
    assert "CREATE TABLE posts" in dump.read_text(encoding="utf-8")


def test_a_pruned_dump_takes_the_migration_files_with_it(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    write_migration(tmp_path, "2020_01_01_000000", "posts")
    assert kernel.run_argv("migrate", []) == 0
    capsys.readouterr()

    assert kernel.run_argv("schema:dump", ["--prune"]) == 0
    assert "Pruned 1 migration file(s)." in capsys.readouterr().out
    assert list((tmp_path / "database" / "migrations").glob("*.py")) == []

    assert kernel.run_argv("schema:dump", ["--database"]) == 2


def test_migrate_loads_a_dump_before_running_anything(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    write_migration(tmp_path, "2020_01_01_000000", "posts")
    assert kernel.run_argv("migrate", []) == 0
    assert kernel.run_argv("schema:dump", []) == 0
    capsys.readouterr()

    # A database that has never seen a migration reads the dump instead.
    kernel = build()
    dump = "database/schema/database-schema.sql"
    assert kernel.run_argv("migrate", ["--schema-path", dump]) == 0
    printed = capsys.readouterr().out
    assert "Loaded" in printed
    assert "Nothing to migrate." in printed
    assert has_table("posts")

    # Second time through, the dump is behind us and is not read again.
    assert kernel.run_argv("migrate", ["--schema-path", dump]) == 0
    assert "Loaded" not in capsys.readouterr().out


def test_migrate_ignores_a_schema_path_that_was_not_given_a_value(
    build: Build, tmp_path: Path
) -> None:
    kernel = build()
    write_migration(tmp_path, "2020_01_01_000000", "posts")

    assert kernel.run_argv("migrate", ["--schema-path"]) == 0
    assert has_table("posts")
