"""Add email_verified_at to users — MustVerifyEmail and UserFactory both want it."""

from __future__ import annotations

from almasix.orm import Migration, Schema


class AddEmailVerifiedAtToUsersTable(Migration):
    async def up(self) -> None:
        await Schema.table(
            "users",
            lambda table: (table.timestamp("email_verified_at").nullable(),),
        )

    async def down(self) -> None:
        await Schema.table(
            "users",
            lambda table: (table.drop_column("email_verified_at"),),
        )
