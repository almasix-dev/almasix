"""Demo JsonResource / ResourceCollection / conditionals / wrapping (M23)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from almasix.console.command import Command
from almasix.http.resources import JsonResource
from app.http.resources.post_resource import PostCollection, PostResource
from app.models.post import Post
from app.support.demo_db import ensure_demo_database


def rendered(response: Any) -> Any:
    return json.loads(response.body.decode())


class ProgressResourcesCommand(Command):
    signature = "progress:resources"
    description = "Demo API resources — conditionals, wrapping, pagination (M23)"

    def handle(self) -> int:
        return asyncio.run(self.demonstrate())

    async def demonstrate(self) -> int:
        await ensure_demo_database()

        lean = await Post.query().published().order_by("id").first()
        self.info(f"lean -> {PostResource(lean).resolve()}")

        eager = await (
            Post.query().published().with_("author").with_count("comments").order_by("id")
        ).first()
        self.info(f"eager -> {PostResource(eager).resolve()}")

        response = PostResource(eager).response()
        self.info(f"wrapped -> {rendered(response)}")

        JsonResource.without_wrapping()
        self.info(f"unwrapped -> {rendered(PostResource(eager).response())}")
        JsonResource.wrap_with("data")

        posts = await (
            Post.query().published().with_("author").with_count("comments").order_by("id")
        ).paginate(2, page=1)
        payload = rendered(PostCollection(posts).response())
        self.info(f"paginated -> {len(payload['data'])} rows, meta {payload['meta']}")
        self.info(f"collection meta -> {payload['meta_extra']}")

        extra = rendered(PostResource(eager).additional({"meta": {"demo": True}}).response())
        self.info(f"additional -> {extra['meta']}")

        self.line("  route: GET /api/resources and /api/resources/1")
        self.success("resources demo ok")
        return 0
