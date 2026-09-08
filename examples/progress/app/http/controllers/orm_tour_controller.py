"""ORM tour — one JSON map of M5 features exercised by this app."""

from __future__ import annotations

from app.models.post import Post
from app.models.user import User
from app.support.demo_db import ensure_demo_database
from almasix.http import Controller


class OrmTourController(Controller):
    async def index(self) -> dict:
        await ensure_demo_database()
        published = await Post.query().published().with_("author").get()
        page = await Post.query().published().order_by("id").paginate(1, page=1)
        trashed = await Post.only_trashed().count()
        authors = await User.query().has("posts", ">=", 1).with_count("posts").get()
        with_roles = await User.query().with_("roles").first()

        # M41 — one of many, defaults, chaperone, aggregates, existence queries.
        latest = await User.query().with_("latest_post").has("posts").first()
        orphan = Post()
        commented = await Post.query().has("comments").with_("comments").first()
        summed = await User.query().with_sum("posts", "views").with_exists("posts").get()
        if summed:
            await summed.load_count("comments")
        publishers = await User.query().where_relation("posts", "published", True).get()
        constrained = await (
            User.query()
            .with_where_has("posts", lambda query: query.where("published", "=", True))
            .first()
        )
        return {
            "features": {
                "eager_load": {
                    "endpoint": "GET /api/posts",
                    "count": len(published),
                    "sample_author": published[0].author.email if published else None,
                },
                "local_scope": {
                    "endpoint": "GET /api/posts",
                    "scope": "published()",
                    "published_titles": [post.title for post in published],
                },
                "pagination": {
                    "endpoint": "GET /api/posts/pages?page=1&per_page=1",
                    "page": page.to_dict(),
                },
                "soft_deletes": {
                    "endpoint": "GET /api/posts/trashed",
                    "trashed_count": trashed,
                },
                "with_count_and_where_has": {
                    "endpoint": "GET /api/users + /api/users/authors",
                    "authors": [
                        {
                            "email": user.email,
                            "posts_count": user._extra.get("posts_count", 0),
                        }
                        for user in authors
                    ],
                },
                "belongs_to_many_pivot": {
                    "endpoint": "GET /api/users",
                    "sample_roles": (
                        [
                            # M41 — the intermediate row arrives as an object.
                            {"name": role.name, "pivot_level": role.pivot.level}
                            for role in with_roles.roles
                        ]
                        if with_roles and with_roles.relation_loaded("roles")
                        else []
                    ),
                },
                "one_of_many": {
                    "relation": "User.latest_post -> has_many(Post).latest_of_many()",
                    "latest_post": latest.latest_post.title if latest else None,
                },
                "default_models": {
                    "relation": "Post.author_or_ghost -> belongs_to(User).with_default(...)",
                    "orphan_author": (await orphan.author_or_ghost().get()).name,
                },
                "chaperone": {
                    "relation": "Post.comments -> morph_many(...).chaperone('commentable')",
                    "child_sees_parent": (
                        commented.comments[0].commentable.title
                        if commented and len(commented.comments)
                        else None
                    ),
                },
                "aggregates": {
                    "endpoint": "GET /api/orm",
                    "sums": [
                        {
                            "email": user.email,
                            "posts_sum_views": user.posts_sum_views,
                            "posts_exists": user.posts_exists,
                        }
                        for user in summed
                    ],
                    "deferred": {"comments_count": summed[0].comments_count if summed else 0},
                },
                "existence_queries": {
                    "where_relation": [user.email for user in publishers],
                    "with_where_has": {
                        "email": constrained.email if constrained else None,
                        "published_posts": (
                            [post.title for post in constrained.posts] if constrained else []
                        ),
                    },
                },
                "morph_many": {
                    "endpoint": "GET /api/posts/1/comments",
                    "hint": "Seed attaches a comment to Ada's first post",
                },
                "upsert": {
                    "endpoint": "POST /api/users/upsert",
                    "body": {"email": "ada@almasix.dev", "name": "Ada Lovelace"},
                },
                "no_lazy_load": {
                    "endpoint": "GET /api/users/1/posts",
                    "contract": "Default: unloaded user.posts raises. Opt in with lazy_relations + await user.posts",
                },
            }
        }
