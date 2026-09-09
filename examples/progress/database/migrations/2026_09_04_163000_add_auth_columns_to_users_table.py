"""Add the token column the M7 API guard reads.

`password`, `remember_token`, and `email_verified_at` arrive with the default
users migration every scaffolded application ships; only the demo's own
`api_token` belongs here.
"""

from __future__ import annotations

from almasix.orm import Migration, Schema


class AddAuthColumnsToUsersTable(Migration):
    async def up(self) -> None:
        await Schema.table(
            "users",
            lambda table: (table.string("api_token").nullable(),),
        )

    async def down(self) -> None:
        await Schema.table(
            "users",
            lambda table: (table.drop_column("api_token"),),
        )
