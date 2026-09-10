"""Demo the query builder and the database layer under it (M42)."""

from __future__ import annotations

import asyncio
import json

from almasix.console.command import Command
from almasix.orm import DB, Schema
from app.models.post import Post
from app.models.user import User
from app.support.demo_db import ensure_demo_database


class ProgressQueriesCommand(Command):
    signature = "progress:queries"
    description = "Demo the query builder + database layer (M42)"

    def handle(self) -> int:
        return asyncio.run(self.demonstrate())

    async def demonstrate(self) -> int:
        await ensure_demo_database()

        seen: list[str] = []
        DB.listen(lambda query: seen.append(query.sql))
        DB.reset_total_query_duration()

        await self.wheres()
        await self.joins_and_unions()
        await self.json_columns()
        await self.writes()
        await self.transactions()
        self.debugging()

        self.line(f"  DB.listen heard {len(seen)} statements")
        self.line(f"  total query time {DB.total_query_duration():.1f}ms")
        self.success("query builder demo ok")
        return 0

    async def wheres(self) -> None:
        loud = await Post.query().where_any(["title", "slug"], "like", "%a%").count()
        self.info(f"where_any -> {loud} posts match on title or slug")

        recent = await DB.table("posts").where_past("created_at").count()
        self.info(f"where_past -> {recent} posts already created")

        authors = (
            await DB.table("users")
            .where_exists(
                DB.table("posts").select_raw("1").where_column("posts.user_id", "users.id")
            )
            .count()
        )
        self.info(f"where_exists -> {authors} users have written something")

        quiet = (
            await DB.table("posts").where_not(lambda query: query.where("views", ">", 0)).count()
        )
        self.info(f"where_not -> {quiet} posts have no views at all")

    async def joins_and_unions(self) -> None:
        busiest = (
            DB.table("posts").select("user_id").select_raw("count(*) as posts").group_by("user_id")
        )
        rows = await (
            DB.table("users")
            .join_sub(busiest, "counts", "counts.user_id", "=", "users.id")
            .select("users.name", "counts.posts")
            .order_by_desc("counts.posts")
            .limit(3)
            .get()
        )
        self.info(f"join_sub -> {[(row['name'], row['posts']) for row in rows]}")

        both = await (
            DB.table("posts")
            .select("title")
            .where("published", True)
            .union(DB.table("posts").select("title").where("views", ">", 100))
            .order_by("title")
            .count()
        )
        self.info(f"union -> {both} distinct titles published or popular")

        spread = await (
            DB.table("posts")
            .group_by("user_id")
            .select("user_id")
            .select_raw("sum(views) as views")
            .having_between("views", [0, 10_000])
            .get()
        )
        self.info(f"having_between -> {len(spread)} authors within the range")

    async def json_columns(self) -> None:
        """JSON paths read and write the same way on every engine."""
        await Schema.drop_if_exists("query_demo")
        await Schema.create(
            "query_demo",
            lambda table: (table.id(), table.string("name"), table.text("options")),
        )
        await DB.table("query_demo").insert(
            [
                {
                    "name": "Ada",
                    "options": json.dumps({"languages": ["en", "fr"], "alerts": {"email": True}}),
                },
                {
                    "name": "Grace",
                    "options": json.dumps({"languages": ["en"], "alerts": {"email": False}}),
                },
            ]
        )

        multilingual = (
            await DB.table("query_demo")
            .where_json_length("options->languages", ">", 1)
            .pluck("name")
        )
        self.info(f"where_json_length -> {list(multilingual)}")

        emailed = await DB.table("query_demo").where("options->alerts->email", True).pluck("name")
        self.info(f"json path where -> {list(emailed)}")

        contains = (
            await DB.table("query_demo")
            .where_json_contains("options->languages", "fr")
            .pluck("name")
        )
        self.info(f"where_json_contains -> {list(contains)}")

        await DB.table("query_demo").where("name", "Grace").update({"options->alerts->email": True})
        updated = json.loads(await DB.table("query_demo").where("name", "Grace").value("options"))
        self.info(f"JSON update -> Grace's document is still {updated}")

    async def writes(self) -> None:
        ignored = await DB.table("query_demo").insert_or_ignore(
            {"id": 1, "name": "Ada", "options": "{}"}
        )
        self.info(f"insert_or_ignore -> {ignored} rows written for a colliding id")

        seeded = DB.table("query_demo").with_attributes({"options": "{}"})
        self.info(f"with_attributes -> query carries {seeded.pending_attributes()}")

        only = await DB.table("query_demo").where("name", "Ada").sole()
        self.info(f"sole -> exactly one {only['name']}")
        self.info(
            f"implode -> {await DB.table('query_demo').order_by('name').implode('name', ', ')}"
        )

        await Schema.drop_if_exists("query_demo")

    async def transactions(self) -> None:
        committed: list[str] = []

        async with DB.transaction():
            DB.after_commit(lambda: committed.append("receipt sent"))
            await DB.table("users").where("id", 0).lock_for_update().get()
            self.info(f"transaction_level -> {DB.transaction_level()} inside the block")
        self.info(f"after_commit -> {committed}")

        planned = await DB.pretend(lambda: User.query().where("id", 0).delete())
        self.info(
            f"DB.pretend -> would have run: {planned[0].sql.split()[0].lower()} (nothing did)"
        )

    def debugging(self) -> None:
        query = DB.table("users").where("name", "Ada").where("id", ">", 1)
        self.info(f"to_sql -> {query.to_sql().replace(chr(10), ' ')}")
        self.info(f"to_raw_sql -> {query.to_raw_sql().replace(chr(10), ' ')}")
        self.info(f"get_bindings -> {query.get_bindings()}")
