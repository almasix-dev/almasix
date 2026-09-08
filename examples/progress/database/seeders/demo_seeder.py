"""DemoSeeder — Progress living-example rows."""

from __future__ import annotations

from app.models.post import Post
from app.models.role import Role
from app.models.user import User
from almasix.hashing import Hash
from almasix.orm import Seeder


class DemoSeeder(Seeder):
    """Seed users, roles, posts, and comments for the ORM tour."""

    async def run(self) -> None:
        if await User.query().count() > 0:
            return

        password = Hash.make("password")
        ada = await User.create(
            email="ada@almasix.dev",
            name="Ada",
            password=password,
            api_token="secret-token",
        )
        grace = await User.create(
            email="grace@almasix.dev",
            name="Grace",
            password=password,
        )
        admin = await Role.create(name="admin")
        editor = await Role.create(name="editor")
        await ada.roles().attach(admin, {"level": "lead"})
        await ada.roles().attach(editor, {"level": "writer"})
        await grace.roles().attach(editor)

        notes = await Post.create(
            title="Notes on engines",
            user_id=ada.id,
            published=True,
            views=3,
        )
        await Post.create(
            title="Eager loading",
            user_id=ada.id,
            published=True,
            views=1,
        )
        draft = await Post.create(
            title="Draft: soft deletes",
            user_id=grace.id,
            published=False,
            views=0,
        )
        await notes.comments().create(body="Ship it.")
        await ada.comments().create(body="From the author profile.")
        await draft.delete()
