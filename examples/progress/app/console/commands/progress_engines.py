"""Demo multi-engine database conformance (M44).

Runs the dialect probe — schema DDL, upsert, JSON wheres, locking,
transactions, and pagination — against the app's default connection, and
names which engines CI executes.
"""

from __future__ import annotations

import asyncio
import json

from almasix.console.command import Command
from almasix.orm import DB, Schema
from app.support.demo_db import ensure_demo_database

# Engines the GitHub Actions orm-engines job executes (not merely compiles).
CI_ENGINES = ("sqlite", "pgsql", "mysql")


class ProgressEnginesCommand(Command):
    signature = "progress:engines"
    description = "Demo multi-engine database CI — DDL, upsert, JSON, locks, tx, pagination"

    def handle(self) -> int:
        return asyncio.run(self.demonstrate())

    async def demonstrate(self) -> int:
        await ensure_demo_database()

        dialect = DB.connection().dialect
        self.info(f"active engine -> {dialect} (app default connection)")
        self.info(f"CI executes -> {', '.join(CI_ENGINES)} (SQL Server / Oracle: compile-only)")

        await self.schema_ddl()
        await self.upsert()
        await self.json_wheres()
        await self.locks_and_transactions()
        await self.pagination()

        await Schema.drop_if_exists("engine_demo")
        self.success("multi-engine database demo ok")
        return 0

    async def schema_ddl(self) -> None:
        await Schema.drop_if_exists("engine_demo")
        await Schema.create(
            "engine_demo",
            lambda table: (
                table.id(),
                table.string("email"),
                table.string("name"),
                table.json("meta").nullable(),
                table.unique(["email"]),
            ),
        )
        columns = await Schema.columns("engine_demo")
        self.info(f"Schema.create -> {len(columns)} columns on {DB.connection().dialect}")

    async def upsert(self) -> None:
        written = await DB.table("engine_demo").upsert(
            {"email": "a@b.c", "name": "Ada", "meta": None},
            unique_by=["email"],
            update=["name"],
        )
        await DB.table("engine_demo").upsert(
            {"email": "a@b.c", "name": "Updated", "meta": None},
            unique_by=["email"],
            update=["name"],
        )
        name = await DB.table("engine_demo").where("email", "a@b.c").value("name")
        self.info(f"upsert -> wrote {written}, then name={name!r}")

    async def json_wheres(self) -> None:
        await DB.table("engine_demo").insert(
            {
                "email": "g@b.c",
                "name": "Grace",
                "meta": json.dumps({"languages": ["en", "fr"], "alerts": {"email": True}}),
            }
        )
        multilingual = await (
            DB.table("engine_demo")
            .where_json_length("meta->languages", ">", 1)
            .pluck("name")
        )
        contains = await (
            DB.table("engine_demo")
            .where_json_contains("meta->languages", "fr")
            .pluck("name")
        )
        self.info(f"where_json_length -> {list(multilingual)}")
        self.info(f"where_json_contains -> {list(contains)}")

    async def locks_and_transactions(self) -> None:
        async with DB.transaction():
            rows = await DB.table("engine_demo").where("email", "a@b.c").lock_for_update().get()
            level = DB.transaction_level()
            self.info(f"lock_for_update -> {len(rows)} row(s) at transaction_level={level}")

        with_savepoint = 0
        async with DB.transaction():
            try:
                async with DB.transaction():
                    await DB.table("engine_demo").insert(
                        {"email": "x@y.z", "name": "X", "meta": None}
                    )
                    raise RuntimeError("roll the savepoint")
            except RuntimeError:
                with_savepoint = await DB.table("engine_demo").where("email", "x@y.z").count()
        self.info(f"nested savepoint -> inner row count after rollback={with_savepoint}")

    async def pagination(self) -> None:
        await DB.table("engine_demo").insert(
            [
                {"email": f"u{n}@ex.com", "name": f"User {n}", "meta": None}
                for n in range(1, 6)
            ]
        )
        page = await DB.table("engine_demo").order_by("id").paginate(2, 1)
        cursor = await DB.table("engine_demo").order_by("id").cursor_paginate(2)
        self.info(f"paginate -> page 1 has {len(list(page))} of {page.total}")
        self.info(f"cursor_paginate -> {len(list(cursor))} rows, has_more={cursor.has_more_pages()}")
