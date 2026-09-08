"""M5 — Schema builder and migrator."""

from __future__ import annotations

from pathlib import Path

import pytest

from almasix.orm import Migration, Migrator, Schema, make_migration
from tests.orm_support import memory_db  # noqa: F401

pytestmark = pytest.mark.asyncio


async def test_schema_create_has_drop(memory_db) -> None:
    await Schema.create("notes", lambda table: (table.id(), table.string("body")))
    assert await Schema.has_table("notes")
    assert "notes" in await Schema.table_names()
    await Schema.drop("notes")
    assert not await Schema.has_table("notes")


async def test_schema_table_add_and_drop_column(memory_db) -> None:
    await Schema.create("posts", lambda table: (table.id(), table.string("title")))
    await Schema.table("posts", lambda table: (table.string("slug").nullable(),))
    assert await Schema.has_column("posts", "slug")
    await Schema.table("posts", lambda table: table.drop_column("slug"))
    assert not await Schema.has_column("posts", "slug")
    # Empty alter is a no-op.
    await Schema.table("posts", lambda table: ())


async def test_schema_table_add_index(memory_db) -> None:
    await Schema.create("posts", lambda table: (table.id(), table.string("title")))
    await Schema.table(
        "posts",
        lambda table: (table.string("slug").nullable(), table.index(["slug"])),
    )
    assert await Schema.has_column("posts", "slug")


async def test_migrator_run_rollback_round_trip(memory_db, tmp_path: Path) -> None:
    path = make_migration(
        "create_notes_table",
        tmp_path,
        table="notes",
        create=True,
    )
    assert path.name.endswith("create_notes_table.py")

    migrator = Migrator(tmp_path)
    applied = await migrator.run()
    assert len(applied) == 1
    assert await Schema.has_table("notes")
    status = await migrator.status()
    assert status[0]["ran"] is True

    rolled = await migrator.rollback()
    assert rolled == applied
    assert not await Schema.has_table("notes")


async def test_migrator_fresh(memory_db, tmp_path: Path) -> None:
    class CreateExtras(Migration):
        async def up(self) -> None:
            await Schema.create("extras", lambda table: (table.id(), table.string("name")))

        async def down(self) -> None:
            await Schema.drop_if_exists("extras")

    # Write a real file so Migrator can load it.
    file = tmp_path / "2020_01_01_000000_create_extras_table.py"
    file.write_text(
        "from almasix.orm import Migration, Schema\n"
        "class CreateExtras(Migration):\n"
        "    async def up(self):\n"
        "        await Schema.create('extras', lambda t: (t.id(), t.string('name')))\n"
        "    async def down(self):\n"
        "        await Schema.drop_if_exists('extras')\n",
        encoding="utf-8",
    )
    migrator = Migrator(tmp_path)
    await migrator.run()
    await Schema.create("stray", lambda table: (table.id(),))
    await migrator.fresh()
    assert await Schema.has_table("extras")
    assert not await Schema.has_table("stray")
