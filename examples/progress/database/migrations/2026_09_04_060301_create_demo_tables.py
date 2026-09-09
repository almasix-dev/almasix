"""Create the Progress demo tables (users, posts, roles, comments)."""

from __future__ import annotations

from almasix.orm import Migration, Schema


class CreateDemoTables(Migration):
    """Schema for the living-example ORM tour."""

    async def up(self) -> None:
        # `users` comes from the default migration every scaffolded app ships.
        await Schema.create(
            "posts",
            lambda table: (
                table.id(),
                table.string("title"),
                table.integer("user_id"),
                table.boolean("published").default(False),
                table.integer("views").default(0),
                table.timestamps(),
                table.soft_deletes(),
            ),
        )
        await Schema.create(
            "roles",
            lambda table: (table.id(), table.string("name")),
        )
        await Schema.create(
            "role_user",
            lambda table: (
                table.integer("role_id"),
                table.integer("user_id"),
                table.string("level").nullable(),
            ),
        )
        await Schema.create(
            "comments",
            lambda table: (
                table.id(),
                table.string("body"),
                table.morphs("commentable"),
            ),
        )

    async def down(self) -> None:
        await Schema.drop_if_exists("comments")
        await Schema.drop_if_exists("role_user")
        await Schema.drop_if_exists("roles")
        await Schema.drop_if_exists("posts")
