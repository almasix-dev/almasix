"""Demo the schema builder, the migrator, and the paginators (M43)."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from almasix.console.command import Command
from almasix.orm import DB, Migrator, Schema
from app.support.demo_db import ensure_demo_database

MIGRATION = '''
from almasix.orm import Migration, Schema


class AddNicknameToSchemaDemoTable(Migration):
    async def up(self) -> None:
        await Schema.table("schema_demo", lambda table: table.string("nickname").nullable())

    async def down(self) -> None:
        await Schema.table("schema_demo", lambda table: table.drop_column("nickname"))
'''


class ProgressSchemaCommand(Command):
    signature = "progress:schema"
    description = "Demo the schema builder, migrations, and pagination (M43)"

    def handle(self) -> int:
        return asyncio.run(self.demonstrate())

    async def demonstrate(self) -> int:
        await ensure_demo_database()

        await self.build_a_table()
        await self.alter_it()
        await self.inspect_it()
        await self.migrate()
        await self.paginate()

        await Schema.drop_if_exists("schema_demo")
        self.success("schema, migration, and pagination demo ok")
        return 0

    async def build_a_table(self) -> None:
        """The column catalogue: one blueprint, whichever engine is behind it."""
        await Schema.drop_if_exists("schema_demo")
        await Schema.create(
            "schema_demo",
            lambda table: (
                table.id(),
                table.string("name"),
                table.char("initials", 3).nullable(),
                table.unsigned_small_integer("votes").default(0),
                table.enum("kind", ["reader", "author"]).default("reader"),
                table.jsonb("preferences").nullable(),
                table.ip_address("last_seen_at_ip").nullable(),
                table.ulid("token").nullable(),
                table.timestamp("joined_at").use_current(),
                table.soft_deletes_tz(),
                table.nullable_morphs("owner"),
                table.foreign_id("user_id").nullable().constrained("users").null_on_delete(),
                table.index(["kind", "votes"]),
            ),
        )
        self.info(f"Schema.create -> {len(await Schema.columns('schema_demo'))} columns from one blueprint")

    async def alter_it(self) -> None:
        """change() restates a column; the drops undo what the helpers added."""
        await Schema.table(
            "schema_demo",
            lambda table: (
                table.string("summary").nullable().comment("What this row is for"),
                table.rename_column("name", "display_name"),
                table.unique("token"),
                table.drop_morphs("owner"),
            ),
        )
        self.info("Schema.table -> added, renamed, indexed, and dropped in one pass")

        await Schema.rename("schema_demo", "schema_demo_renamed")
        await Schema.rename("schema_demo_renamed", "schema_demo")
        self.info(f"Schema.rename -> round trip, table is {await Schema.has_table('schema_demo')}")

        pretended = await DB.pretend(
            lambda: Schema.table("schema_demo", lambda table: table.string("subtitle", 80).nullable())
        )
        self.info(f"DB.pretend -> would have run: {pretended[0].sql.split('ADD')[0].strip()} ADD …")

    async def inspect_it(self) -> None:
        """Everything the builder can create, the inspector can read back."""
        self.info(f"has_columns -> {await Schema.has_columns('schema_demo', ['display_name', 'votes'])}")
        self.info(f"column_type -> votes is {await Schema.column_type('schema_demo', 'votes')}")
        indexes = await Schema.get_indexes("schema_demo")
        self.info(f"get_indexes -> {[index['name'] for index in indexes]}")
        keys = await Schema.get_foreign_keys("schema_demo")
        self.info(f"get_foreign_keys -> user_id points at {[key['foreign_table'] for key in keys]}")

    async def migrate(self) -> None:
        """A migration run, pretended, stepped, and rolled back."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "2026_01_01_000000_add_nickname_to_schema_demo_table.py"
            path.write_text(MIGRATION)
            await self.migrate_from(Migrator(directory))

    async def migrate_from(self, migrator: Migrator) -> None:
        migrator.table = "schema_demo_migrations"

        planned = await migrator.run(pretend=True)
        self.info(f"migrate --pretend -> {len(planned[0].queries)} statement(s), none of them run")

        ran = await migrator.run(step=True)
        self.info(f"migrate --step -> {ran[0]} in {ran[0].elapsed:.0f}ms, batch of its own")
        self.info(f"status -> {[(row['migration'], row['batch']) for row in await migrator.status()]}")

        back = await migrator.rollback(step=1)
        self.info(f"migrate:rollback --step=1 -> undid {len(back)}, nickname gone: "
                  f"{not await Schema.has_column('schema_demo', 'nickname')}")
        await DB.statement(f'DROP TABLE IF EXISTS "{migrator.table}"')

    async def paginate(self) -> None:
        """Three paginators, and the links the first one writes."""
        await DB.table("schema_demo").insert(
            [{"display_name": f"Reader {number}", "votes": number} for number in range(1, 11)]
        )

        def readers():
            return DB.table("schema_demo").order_by("id")

        page = await readers().paginate(3)
        self.info(f"paginate -> page {page.current_page} of {page.last_page}, {page.total} rows in all")
        self.info(f"           next is {page.next_page_url()}")

        simple = await readers().simple_paginate(3)
        self.info(f"simple_paginate -> no count query, has_more_pages={simple.has_more_pages()}")

        first = await readers().cursor_paginate(3)
        second = await readers().cursor_paginate(3, first.next_cursor())
        self.info(
            f"cursor_paginate -> {[row['votes'] for row in first]} then {[row['votes'] for row in second]}"
        )
        self.info(f"           back again -> {second.previous_page_url()}")

        links = page.links()
        self.info(f"links() -> {links.count('<a')} anchors rendered through Prism")
