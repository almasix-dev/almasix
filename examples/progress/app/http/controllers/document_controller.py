"""Documents tour — M25: Articulate reading and writing a document store."""

from __future__ import annotations

from app.models.activity import Activity
from app.models.user import User
from app.support.demo_db import ensure_demo_database

from almasix.http import Controller
from almasix.orm import UnsupportedQueryError
from almasix.orm.facade import get_manager


class DocumentController(Controller):
    async def index(self) -> dict:
        await ensure_demo_database()
        await Activity.query().without_global_scopes().delete()

        ada = await User.query().where("email", "=", "ada@almasix.dev").first()
        viewed = await Activity.create(
            action="viewed", user_id=ada.id, weight=3, tags=["demo", "read"]
        )
        await viewed.get_relation("location").create(city="Nairobi", country="KE")
        await Activity.factory().count(3).heavy().create({"user_id": ada.id})

        page = await Activity.query().order_by_desc("weight").paginate(2, page=1)
        with_user = await Activity.query().with_("user").first()

        try:
            Activity.query().join("users", "id", "=", "user_id")
            refusal = None
        except UnsupportedQueryError as exc:
            refusal = str(exc)

        store = Activity.get_store()
        return {
            "store": {
                "driver": store.driver,
                "connection": Activity.connection,
                "collection": Activity.get_table(),
                "document_connections": get_manager().document_connection_names(),
                "indexes": [index["name"] for index in await store.indexes("activities")],
            },
            "documents": {
                "count": await Activity.query().count(),
                "heavy": await Activity.query().heavy().count(),
                "tagged_demo": await Activity.query().where_all("tags", ["demo"]).count(),
                "total_weight": await Activity.query().sum("weight"),
                "page": page.to_dict(),
            },
            "embedded": (await Activity.find(viewed.get_key())).get_raw_attribute("location"),
            "reference": {
                "user_id": with_user.user_id,
                "user": with_user.user.name,
                "note": "the key lives in the document; the user lives in SQL",
            },
            "soft_deletes": {
                "visible": await Activity.query().count(),
                "with_trashed": await Activity.with_trashed().count(),
            },
            "sql_only": refusal,
        }
