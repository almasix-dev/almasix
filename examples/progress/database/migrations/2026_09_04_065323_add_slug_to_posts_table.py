"""Alter the posts table."""

from __future__ import annotations

from almasix.orm import Migration, Schema


class AddSlugToPostsTable(Migration):
    """AddSlugToPostsTable."""

    async def up(self) -> None:
        await Schema.table(
            "posts",
            lambda table: (
                table.string("slug").unique().after("title")
            ),
        )

    async def down(self) -> None:
        await Schema.table(
            "posts",
            lambda table: (
                table.drop_column("slug")
            ),
        )
