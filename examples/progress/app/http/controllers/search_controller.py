"""Search tour — M27: Scout-class search over the posts table."""

from __future__ import annotations

from almasix.http import Controller, Request
from almasix.scout import Scout, get_engine_manager
from app.models.post import Post
from app.support.demo_db import ensure_demo_database


class SearchController(Controller):
    async def index(self, request: Request) -> dict:
        await ensure_demo_database()
        manager = get_engine_manager()
        phrase = str(request.query("q", "engines") or "")

        results = await Post.search(phrase).get()
        page = await Post.search("").order_by("id").paginate(per_page=2, page=1)
        keys = await Post.search("").keys()

        configured = manager.get_default_driver()
        Scout.use("collection")
        in_memory = await Post.search(phrase).get()
        Scout.use(configured)

        fake = Scout.fake()
        await Post.query().searchable()
        written = fake.written("update")
        Scout.set_manager(manager)

        return {
            "engine": {
                "driver": configured,
                "index": Post.searchable_as(),
                "queued": manager.queues,
                "soft_deletes_indexed": manager.soft_delete,
            },
            "search": {
                "query": phrase,
                "hits": [{"id": post.id, "title": post.title} for post in results],
                "keys": keys,
                "count": await Post.search(phrase).count(),
            },
            "collection_engine": [post.title for post in in_memory],
            "pagination": page.to_dict(),
            "indexing": {
                "documents": written[0].documents if written else [],
                "note": "only published posts are searchable — should_be_searchable()",
            },
        }
