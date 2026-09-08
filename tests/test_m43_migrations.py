"""What a migration run does now: transactions, pretend, steps, events, squashing."""

from __future__ import annotations

from pathlib import Path

import pytest

from almasix.events.helpers import listen, set_dispatcher
from almasix.orm import Schema
from almasix.orm.facade import DB
from almasix.orm.migration import (
    MigrationEnded,
    MigrationError,
    MigrationStarted,
    Migrator,
    NoPendingMigrations,
)
from tests.orm_support import memory_db  # noqa: F401

pytestmark = pytest.mark.asyncio


def write(directory: Path, stamp: str, table: str, *, body: str = "", extra: str = "") -> str:
    """A create/drop migration for ``table``, returning its name."""
    directory.mkdir(parents=True, exist_ok=True)
    name = f"{stamp}_create_{table}_table"
    (directory / f"{name}.py").write_text(
        "from almasix.orm import Migration, Schema\n"
        f"class Create{table.capitalize()}Table(Migration):\n"
        f"{extra}"
        "    async def up(self):\n"
        f"        await Schema.create('{table}', lambda t: (t.id(), t.string('name')))\n"
        f"{body}"
        "    async def down(self):\n"
        f"        await Schema.drop_if_exists('{table}')\n",
        encoding="utf-8",
    )
    return name


# --- steps and batches ------------------------------------------------------


async def test_step_gives_each_migration_a_batch_of_its_own(memory_db, tmp_path: Path) -> None:
    write(tmp_path, "2020_01_01_000000", "posts")
    write(tmp_path, "2020_01_02_000000", "tags")
    migrator = Migrator(tmp_path)

    await migrator.run(step=True)
    assert await migrator.batches() == {
        "2020_01_01_000000_create_posts_table": 1,
        "2020_01_02_000000_create_tags_table": 2,
    }

    # The last batch is one migration, so a plain rollback undoes only that.
    rolled = await migrator.rollback()
    assert rolled == ["2020_01_02_000000_create_tags_table"]
    assert await Schema.has_table("posts")


async def test_rolling_back_counts_migrations_the_way_laravel_counts_them(
    memory_db, tmp_path: Path
) -> None:
    write(tmp_path, "2020_01_01_000000", "posts")
    write(tmp_path, "2020_01_02_000000", "tags")
    write(tmp_path, "2020_01_03_000000", "notes")
    migrator = Migrator(tmp_path)
    await migrator.run()  # one batch of three

    rolled = await migrator.rollback(step=2)
    assert rolled == [
        "2020_01_03_000000_create_notes_table",
        "2020_01_02_000000_create_tags_table",
    ]
    assert await Schema.has_table("posts")
    assert not await Schema.has_table("tags")


async def test_rolling_back_one_batch_by_number(memory_db, tmp_path: Path) -> None:
    write(tmp_path, "2020_01_01_000000", "posts")
    migrator = Migrator(tmp_path)
    await migrator.run()
    write(tmp_path, "2020_01_02_000000", "tags")
    await migrator.run()

    rolled = await migrator.rollback(batch=1)
    assert rolled == ["2020_01_01_000000_create_posts_table"]
    assert await Schema.has_table("tags")
    assert not await Schema.has_table("posts")


async def test_running_a_capped_number_of_migrations(memory_db, tmp_path: Path) -> None:
    write(tmp_path, "2020_01_01_000000", "posts")
    write(tmp_path, "2020_01_02_000000", "tags")
    migrator = Migrator(tmp_path)

    assert len(await migrator.run(1)) == 1
    assert not await Schema.has_table("tags")
    assert await migrator.pending()


async def test_refresh_can_count_migrations_too(memory_db, tmp_path: Path) -> None:
    write(tmp_path, "2020_01_01_000000", "posts")
    write(tmp_path, "2020_01_02_000000", "tags")
    migrator = Migrator(tmp_path)
    await migrator.run()

    rolled, applied = await migrator.refresh(step=1)
    assert rolled == ["2020_01_02_000000_create_tags_table"]
    assert applied == ["2020_01_02_000000_create_tags_table"]

    rolled, applied = await migrator.refresh()
    assert len(rolled) == 2 and len(applied) == 2


async def test_a_migrator_reads_every_path_it_is_given(memory_db, tmp_path: Path) -> None:
    write(tmp_path / "one", "2020_01_01_000000", "posts")
    write(tmp_path / "two", "2020_01_02_000000", "tags")
    migrator = Migrator([tmp_path / "one", tmp_path / "two"])

    applied = await migrator.run()
    assert applied == [
        "2020_01_01_000000_create_posts_table",
        "2020_01_02_000000_create_tags_table",
    ]
    assert migrator.path == tmp_path / "one"
    assert Migrator([]).path == Path("database/migrations")


# --- pretend ------------------------------------------------------------------


async def test_pretend_prints_the_statements_and_runs_none_of_them(
    memory_db, tmp_path: Path
) -> None:
    write(tmp_path, "2020_01_01_000000", "posts")
    migrator = Migrator(tmp_path)

    applied = await migrator.run(pretend=True)
    assert len(applied) == 1
    assert any("CREATE TABLE posts" in query.sql for query in applied[0].queries)
    assert not await Schema.has_table("posts")
    assert await migrator.pending()  # nothing was recorded either


async def test_pretending_to_roll_back(memory_db, tmp_path: Path) -> None:
    write(tmp_path, "2020_01_01_000000", "posts")
    migrator = Migrator(tmp_path)
    await migrator.run()

    rolled = await migrator.rollback(pretend=True)
    assert any("DROP TABLE" in query.sql for query in rolled[0].queries)
    assert await Schema.has_table("posts")
    assert await migrator.ran() == ["2020_01_01_000000_create_posts_table"]

    rolled, applied = await migrator.refresh(pretend=True)
    assert rolled and applied == []
    assert await Schema.has_table("posts")


# --- transactions and the migration's own settings --------------------------------


async def test_a_migration_that_fails_halfway_takes_its_writes_with_it(
    memory_db, tmp_path: Path
) -> None:
    """The migration runs in a transaction, so a failure undoes what it wrote."""
    write(tmp_path, "2020_01_01_000000", "posts")
    (tmp_path / "2020_01_02_000000_seed_posts.py").write_text(
        "from almasix.orm import DB, Migration\n"
        "class SeedPosts(Migration):\n"
        "    async def up(self):\n"
        "        await DB.table('posts').insert({'name': 'First'})\n"
        "        raise RuntimeError('halfway')\n"
        "    async def down(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    migrator = Migrator(tmp_path)

    with pytest.raises(RuntimeError, match="halfway"):
        await migrator.run()

    assert await DB.table("posts").count() == 0
    assert await migrator.ran() == ["2020_01_01_000000_create_posts_table"]


async def test_a_migration_can_opt_out_of_the_transaction(memory_db, tmp_path: Path) -> None:
    write(tmp_path, "2020_01_01_000000", "posts", extra="    within_transaction = False\n")
    migrator = Migrator(tmp_path)

    assert len(await migrator.run()) == 1
    assert await Schema.has_table("posts")


async def test_a_migration_that_says_it_should_not_run_is_skipped(
    memory_db, tmp_path: Path
) -> None:
    write(
        tmp_path,
        "2020_01_01_000000",
        "posts",
        extra="    def should_run(self):\n        return False\n",
    )
    write(tmp_path, "2020_01_02_000000", "tags")
    migrator = Migrator(tmp_path)

    applied = await migrator.run()
    assert applied == ["2020_01_02_000000_create_tags_table"]
    assert not await Schema.has_table("posts")

    # It is not recorded, so it stays pending rather than being counted as done.
    assert [path.stem for path in await migrator.pending()] == [
        "2020_01_01_000000_create_posts_table"
    ]
    assert applied[0].migration == "2020_01_02_000000_create_tags_table"

    rolled = await migrator.rollback()
    assert rolled == ["2020_01_02_000000_create_tags_table"]

    # A migration that declines to run declines to be rolled back as well.
    await DB.statement(
        'INSERT INTO "migrations" (migration, batch) VALUES (:migration, :batch)',
        {"migration": "2020_01_01_000000_create_posts_table", "batch": 1},
    )
    assert await migrator.rollback() == []


async def test_a_file_that_is_not_a_migration_is_not_one(memory_db, tmp_path: Path) -> None:
    write(tmp_path, "2020_01_01_000000", "posts")
    (tmp_path / "helpers.py").write_text("VALUE = 1\n", encoding="utf-8")

    assert [path.name for path in Migrator(tmp_path).files()] == [
        "2020_01_01_000000_create_posts_table.py"
    ]


async def test_a_migration_naming_its_own_connection(memory_db, tmp_path: Path) -> None:
    write(tmp_path, "2020_01_01_000000", "posts", extra="    connection = 'sqlite'\n")
    migrator = Migrator(tmp_path)
    assert len(await migrator.run()) == 1
    assert await Schema.has_table("posts")


# --- events ---------------------------------------------------------------------------


async def test_a_run_announces_what_it_is_doing(memory_db, tmp_path: Path) -> None:
    heard: list[object] = []
    set_dispatcher(None)
    listen(MigrationStarted, lambda event: heard.append(event))
    listen(MigrationEnded, lambda event: heard.append(event))
    listen(NoPendingMigrations, lambda event: heard.append(event))

    write(tmp_path, "2020_01_01_000000", "posts")
    migrator = Migrator(tmp_path)
    await migrator.run()
    await migrator.run()

    assert isinstance(heard[0], MigrationStarted)
    assert heard[0].direction == "up"
    assert isinstance(heard[1], MigrationEnded)
    assert heard[1].elapsed > 0
    assert isinstance(heard[2], NoPendingMigrations)


async def test_a_listener_that_throws_does_not_stop_the_migration(
    memory_db, tmp_path: Path
) -> None:
    set_dispatcher(None)

    def explode(event: object) -> None:
        raise RuntimeError("listener")

    listen(MigrationStarted, explode)
    write(tmp_path, "2020_01_01_000000", "posts")

    assert len(await Migrator(tmp_path).run()) == 1
    assert await Schema.has_table("posts")


# --- the repository ----------------------------------------------------------------------


async def test_the_repository_is_named_the_way_this_engine_names_things(
    memory_db, tmp_path: Path
) -> None:
    """It used to be double-quoted by hand, which MySQL reads as a string."""
    migrator = Migrator(tmp_path)
    await migrator._ensure_table()
    assert migrator._quoted_table() == '"migrations"'


async def test_a_recorded_migration_whose_file_has_gone(memory_db, tmp_path: Path) -> None:
    migrator = Migrator(tmp_path)
    await migrator._ensure_table()
    await DB.statement(
        'INSERT INTO "migrations" (migration, batch) VALUES (:migration, :batch)',
        {"migration": "2020_01_01_000000_create_ghosts_table", "batch": 1},
    )
    with pytest.raises(MigrationError, match="file missing"):
        await migrator.rollback()


async def test_rolling_back_nothing_at_all(memory_db, tmp_path: Path) -> None:
    migrator = Migrator(tmp_path)
    assert await migrator.rollback() == []
    assert await migrator.reset() == []
    assert await migrator.run() == []


async def test_fresh_drops_tables_that_point_at_each_other(memory_db, tmp_path: Path) -> None:
    """Dropping in inspector order used to trip over a foreign key."""
    (tmp_path / "2020_01_01_000000_create_posts_table.py").write_text(
        "from almasix.orm import Migration, Schema\n"
        "class CreatePostsTable(Migration):\n"
        "    async def up(self):\n"
        "        await Schema.create('users', lambda t: t.id())\n"
        "        await Schema.create('posts', lambda t: ("
        "t.id(), t.foreign_id('user_id').constrained()))\n"
        "    async def down(self):\n"
        "        await Schema.drop_if_exists('posts')\n",
        encoding="utf-8",
    )
    migrator = Migrator(tmp_path)
    await migrator.run()
    await DB.statement("PRAGMA foreign_keys=ON")

    assert len(await migrator.fresh()) == 1
    assert set(await Schema.table_names()) == {"migrations", "users", "posts"}


# --- squashing -----------------------------------------------------------------------------


async def test_a_schema_dump_can_be_replayed_on_an_empty_database(
    memory_db, tmp_path: Path
) -> None:
    write(tmp_path, "2020_01_01_000000", "posts")
    migrator = Migrator(tmp_path)
    await migrator.run()
    await Schema.table("posts", lambda table: table.string("slug").nullable().index())

    dump = await migrator.dump_schema(tmp_path / "schema" / "sqlite-schema.sql")
    text = dump.read_text(encoding="utf-8")
    assert "CREATE TABLE posts" in text
    assert "CREATE INDEX ix_posts_slug" in text
    assert "2020_01_01_000000_create_posts_table" in text

    await Schema.drop_all_tables()
    count = await migrator.load_schema(dump)
    assert count > 0
    assert await Schema.has_column("posts", "slug")
    # The dump carries the migration history, so nothing is pending after it.
    assert await migrator.pending() == []


async def test_loading_a_dump_that_is_not_there(memory_db, tmp_path: Path) -> None:
    with pytest.raises(MigrationError, match="No schema dump"):
        await Migrator(tmp_path).load_schema(tmp_path / "missing.sql")


async def test_status_says_which_batch_each_migration_ran_in(memory_db, tmp_path: Path) -> None:
    write(tmp_path, "2020_01_01_000000", "posts")
    write(tmp_path, "2020_01_02_000000", "tags")
    migrator = Migrator(tmp_path)
    await migrator.run(1)

    status = await migrator.status()
    assert status[0] == {
        "migration": "2020_01_01_000000_create_posts_table",
        "ran": True,
        "batch": 1,
    }
    assert status[1]["ran"] is False and status[1]["batch"] is None
