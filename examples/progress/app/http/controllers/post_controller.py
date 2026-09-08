"""ORM demo — posts: scopes, eager load, soft deletes, morph comments, pagination."""

from __future__ import annotations

from app.models.post import Post
from app.support.demo_db import ensure_demo_database
from almasix.http import Controller, Request
from almasix.http.exceptions import NotFoundHttpException
from almasix.orm import ModelNotFoundError


class PostController(Controller):
    async def index(self) -> dict:
        """Published posts with eager-loaded authors (no N+1)."""
        await ensure_demo_database()
        posts = await Post.query().published().with_("author").order_by("id").get()
        return {"posts": posts.to_dict(), "count": len(posts)}

    async def pages(self, request: Request) -> dict:
        """Length-aware pagination."""
        await ensure_demo_database()
        page = int(request.query("page", 1) or 1)
        per_page = int(request.query("per_page", 1) or 1)
        result = await Post.query().published().order_by("id").paginate(per_page, page=page)
        return result.to_dict()

    async def trashed(self) -> dict:
        """Soft-deleted posts only."""
        await ensure_demo_database()
        posts = await Post.only_trashed().with_("author").order_by("id").get()
        return {"posts": posts.to_dict(), "count": len(posts)}

    async def trash(self, post: str) -> dict:
        await ensure_demo_database()
        model = await _post_or_fail(int(post), with_trashed=True)
        await model.delete()
        return {"id": model.id, "trashed": model.trashed()}

    async def restore(self, post: str) -> dict:
        await ensure_demo_database()
        model = await _post_or_fail(int(post), with_trashed=True)
        await model.restore()
        return {"id": model.id, "trashed": model.trashed(), "published": model.published}

    async def comments(self, post: str) -> dict:
        await ensure_demo_database()
        model = await _post_or_fail(int(post))
        comments = await model.comments().order_by("id").get()
        return {"post_id": model.id, "comments": comments.to_dict()}

    async def add_comment(self, post: str, request: Request) -> dict:
        await ensure_demo_database()
        model = await _post_or_fail(int(post))
        body = str(request.input("body", "")).strip() or "Nice post."
        comment = await model.comments().create(body=body)
        return {"comment": comment.to_dict()}


async def _post_or_fail(post_id: int, *, with_trashed: bool = False) -> Post:
    query = Post.with_trashed() if with_trashed else Post.query()
    try:
        return await query.find_or_fail(post_id)
    except ModelNotFoundError as exc:
        raise NotFoundHttpException(f"Post {post_id} not found") from exc
