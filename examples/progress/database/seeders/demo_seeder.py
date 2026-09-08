"""DemoSeeder — Progress living-example rows, built by factories (M24)."""

from __future__ import annotations

from app.models.post import Post
from app.models.role import Role
from app.models.user import User

from almasix.orm import Seeder


class DemoSeeder(Seeder):
    """Seed users, roles, posts, and comments for the ORM tour.

    Every row goes through a factory: the fixed columns the tour asserts on
    are states, and everything else the factory invents.
    """

    async def run(self) -> None:
        if await User.query().count() > 0:
            return

        ada = await User.factory().with_token("secret-token").create(
            {"email": "ada@almasix.dev", "name": "Ada"}
        )
        grace = await User.factory().create({"email": "grace@almasix.dev", "name": "Grace"})

        admin = await Role.factory().create({"name": "admin"})
        editor = await Role.factory().create({"name": "editor"})
        await ada.roles().attach(admin, {"level": "lead"})
        await ada.roles().attach(editor, {"level": "writer"})
        await grace.roles().attach(editor)

        notes = await Post.factory().for_(ada, "author").create(
            {"title": "Notes on engines", "views": 3}
        )
        await Post.factory().for_(ada, "author").create({"title": "Eager loading", "views": 1})
        draft = await (
            Post.factory()
            .draft()
            .for_(grace, "author")
            .create({"title": "Draft: soft deletes"})
        )

        await notes.comments().create(body="Ship it.")
        await ada.comments().create(body="From the author profile.")
        await draft.delete()
