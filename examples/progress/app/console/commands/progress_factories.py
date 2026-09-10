"""Demo model factories — definitions, states, sequences, relations (M24)."""

from __future__ import annotations

import asyncio

from almasix.console.command import Command
from almasix.orm import Collection
from app.models.comment import Comment
from app.models.post import Post
from app.models.role import Role
from app.models.user import User
from app.support.demo_db import ensure_demo_database


class ProgressFactoriesCommand(Command):
    signature = "progress:factories"
    description = "Demo model factories — states, sequences, relationships (M24)"

    def handle(self) -> int:
        return asyncio.run(self.demonstrate())

    async def demonstrate(self) -> int:
        await ensure_demo_database()
        made: list[object] = []

        unsaved = await User.factory().make()
        self.info(f"make -> {unsaved.name} <{unsaved.email}>, saved: {unsaved.exists}")

        raw = await Post.factory().draft().raw()
        self.info(f"raw -> {raw}")

        author = await User.factory().unverified().create({"name": "Factory Ada"})
        made.append(author)
        self.info(f"create -> {author.name}, verified: {author.email_verified_at}")

        posts = await (
            Post.factory()
            .count(4)
            .for_(author, "author")
            .sequence({"published": True}, {"published": False})
            .create()
        )
        made.extend(posts)
        self.info(f"count + sequence -> published {[post.published for post in posts]}")
        self.info(f"for -> every post belongs to user {posts[0].user_id}")

        with_comments = await (
            User.factory()
            .has(Post.factory().count(2).has(Comment.factory().count(2), "comments"), "posts")
            .create()
        )
        made.append(with_comments)
        owned = await Post.query().where("user_id", "=", with_comments.id).get()
        made.extend(owned)
        comments = await Comment.query().where_in("commentable_id", owned.model_keys()).get()
        made.extend(comments)
        self.info(f"has -> {len(owned)} posts, {len(comments)} comments")

        roles = await Role.factory().count(2).create()
        made.extend(roles)
        member = await User.factory().has_attached(roles, {"level": "member"}, "roles").create()
        made.append(member)
        attached = await member.get_relation("roles").get()
        self.info(f"has_attached -> {[role.pivot.level for role in attached]}")

        trashed = await Post.factory().trashed().for_(author, "author").create()
        made.append(trashed)
        self.info(
            f"trashed -> {trashed.trashed()}, hidden from Post.query(): "
            f"{await Post.query().where('id', '=', trashed.id).count() == 0}"
        )

        recycled = await (
            Post.factory().count(3).recycle(author).for_(User.factory(), "author").create()
        )
        made.extend(recycled)
        self.info(f"recycle -> one author for {len(recycled)} posts: {recycled[0].user_id}")

        await member.get_relation("roles").detach()

        removed = 0
        for model in reversed(made):
            await (model.force_delete() if isinstance(model, Post) else model.delete())
            removed += 1
        self.line(f"  cleaned up {removed} demo rows")

        assert isinstance(posts, Collection)
        self.success("factories demo ok")
        return 0
