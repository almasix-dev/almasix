"""Add auth columns to users for M7."""

from __future__ import annotations

from almasix.orm import Migration, Schema


class AddAuthColumnsToUsersTable(Migration):
    async def up(self) -> None:
        await Schema.table(
            "users",
            lambda table: (
                table.string("password").nullable(),
                table.string("remember_token").nullable(),
                table.string("api_token").nullable(),
            ),
        )

    async def down(self) -> None:
        await Schema.table(
            "users",
            lambda table: (
                table.drop_column("password"),
                table.drop_column("remember_token"),
                table.drop_column("api_token"),
            ),
        )
