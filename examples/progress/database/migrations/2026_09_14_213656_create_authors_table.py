"""Create the authors table."""

from __future__ import annotations

from almasix.orm import Blueprint, Migration, Schema


class CreateAuthorsTable(Migration):
    """CreateAuthorsTable."""

    async def up(self) -> None:
        def define(table: Blueprint) -> None:
            table.id()
            table.string('name').index()
            table.string('email').index()
            table.string('phone').nullable()
            table.string('address').nullable()
            table.string('city').nullable()
            table.string('state').nullable()
            table.string('zip').nullable()
            table.string('country').nullable()
            table.string('website').nullable()
            table.string('twitter').nullable()
            table.string('facebook').nullable()
            table.timestamps()

        await Schema.create("authors", define)

    async def down(self) -> None:
        await Schema.drop_if_exists("authors")
