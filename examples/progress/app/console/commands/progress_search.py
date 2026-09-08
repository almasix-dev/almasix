"""Demo Scout-class search — engines, filters, indexing, fakes (M27)."""

from __future__ import annotations

import asyncio

from almasix.console.command import Command
from almasix.scout import Scout, get_engine_manager
from app.models.post import Post
from app.support.demo_db import ensure_demo_database


class ProgressSearchCommand(Command):
    signature = "progress:search"
    description = "Demo search — engines, where clauses, indexing, fakes (M27)"

    def handle(self) -> int:
        return asyncio.run(self.demonstrate())

    async def demonstrate(self) -> int:
        await ensure_demo_database()
        manager = get_engine_manager()

        self.info(f"driver -> {manager.get_default_driver()} [{Post.searchable_as()}]")
        self.info(f"queued -> {'yes' if manager.queues else 'no'}")

        found = await Post.search("engines").get()
        self.info(f"search -> {[post.title for post in found]}")

        first = await Post.search("").order_by("id").first()
        self.info(f"first -> {first.title}")

        filtered = await Post.search("").where("user_id", first.user_id).get()
        self.info(f"where -> {len(filtered)} by user {first.user_id}")

        page = await Post.search("").paginate(per_page=2, page=1)
        self.info(f"paginate -> page 1 of {page.last_page}, {len(page.items)} of {page.total}")

        keys = await Post.search("").take(3).keys()
        self.info(f"keys -> {keys}")

        # The collection engine answers the same questions without SQL.
        configured = manager.get_default_driver()
        Scout.use("collection")
        in_memory = await Post.search("engines").get()
        self.info(f"collection -> {[post.title for post in in_memory]} filtered in Python")
        Scout.use(configured)

        # A fake engine records what would have been indexed.
        fake = Scout.fake()
        await Post.query().searchable()
        indexed = sum(len(write.keys) for write in fake.written("update"))
        self.info(f"index -> {indexed} published post(s) written to [{Post.searchable_as()}]")

        await first.unsearchable()
        fake.assert_removed(first)
        self.info(f"remove -> post {first.get_scout_key()} taken out of the index")

        Scout.set_manager(None)
        self.success("search demo ok")
        return 0
