"""M23 demo — API resources returned straight from a controller."""

from __future__ import annotations

from almasix.http import Controller, Request
from almasix.http.exceptions import NotFoundHttpException
from almasix.orm import ModelNotFoundError
from app.http.resources.post_resource import PostCollection, PostResource
from app.models.post import Post
from app.support.demo_db import ensure_demo_database


class ResourceController(Controller):
    async def index(self, request: Request) -> PostCollection:
        """A paginated collection — `data`, `meta`, and `links` in one return."""
        await ensure_demo_database()
        page = int(request.query("page", 1) or 1)
        per_page = int(request.query("per_page", 2) or 2)
        posts = await (
            Post.query().published().with_("author").with_count("comments").order_by("id")
        ).paginate(per_page, page=page)
        return PostCollection(posts)

    async def show(self, post: str) -> PostResource:
        """One post. `author` appears because it was eager loaded."""
        await ensure_demo_database()
        try:
            model = await Post.query().with_("author").where("id", int(post)).first_or_fail()
        except ModelNotFoundError as exc:
            raise NotFoundHttpException("Post not found") from exc
        return PostResource(model).header("X-Resource", "post")
