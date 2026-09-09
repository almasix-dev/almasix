"""Demo Articulate over a document store — collections, embeds, refs (M25)."""

from __future__ import annotations

import asyncio

from almasix.console.command import Command
from almasix.orm import UnsupportedQueryError
from almasix.orm.facade import get_manager
from app.models.activity import Activity
from app.models.user import User
from app.support.demo_db import ensure_demo_database


class ProgressDocumentsCommand(Command):
    signature = "progress:documents"
    description = "Demo document models — collections, embeds, indexes (M25)"

    def handle(self) -> int:
        return asyncio.run(self.demonstrate())

    async def demonstrate(self) -> int:
        await ensure_demo_database()
        await Activity.query().without_global_scopes().delete()

        store = Activity.get_store()
        self.info(f"store -> {store.driver} [{store.name}], collection {Activity.get_table()}")
        self.info(f"indexes -> {await Activity.sync_indexes()}")

        ada = await User.query().where("email", "=", "ada@almasix.dev").first()

        viewed = await Activity.create(
            action="viewed", user_id=ada.id, weight=3, tags=["demo", "read"]
        )
        await Activity.factory().count(3).heavy().create({"user_id": ada.id})
        self.info(f"create -> {viewed.action} by user {viewed.user_id}, key {viewed.get_key()}")

        self.info(f"count -> {await Activity.query().count()} activities")
        self.info(f"scope -> {await Activity.query().heavy().count()} heavy")
        self.info(f"array where -> {await Activity.query().where_all('tags', ['demo']).count()}")
        self.info(f"aggregate -> total weight {await Activity.query().sum('weight')}")

        page = await Activity.query().order_by_desc("weight").paginate(2, 1)
        self.info(f"paginate -> page 1 of {page.last_page}, {len(page.items)} of {page.total}")

        await viewed.get_relation("location").create(city="Nairobi", country="KE")
        reread = await Activity.find(viewed.get_key())
        where = reread.get_relation("location").get()
        self.info(f"embed -> {where.city}, {where.country} (inside the document)")

        reference = await Activity.query().with_("user").first()
        self.info(f"reference -> the document points at SQL user {reference.user.name}")

        await viewed.delete()
        self.info(
            f"soft delete -> visible {await Activity.query().count()}, "
            f"with trashed {await Activity.with_trashed().count()}"
        )
        await viewed.restore()

        try:
            Activity.query().join("users", "id", "=", "user_id")
        except UnsupportedQueryError as exc:
            self.info(f"refusal -> {exc}")

        self.info(
            "parity -> Eloquent-on-collections shipped; "
            "cache/queue/GridFS/Scout Mongo named as gaps"
        )
        self.line(f"  connections -> {get_manager().document_connection_names()}")
        await Activity.query().without_global_scopes().delete()
        self.success("documents demo ok")
        return 0
