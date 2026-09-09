"""Create personal_access_tokens — Signet PATs (M37)."""

from __future__ import annotations

from typing import Any

from almasix.orm import Migration, Schema


class CreatePersonalAccessTokensTable(Migration):
    """CreatePersonalAccessTokensTable."""

    async def up(self) -> None:
        await Schema.create("personal_access_tokens", self.tokens)

    async def down(self) -> None:
        await Schema.drop_if_exists("personal_access_tokens")

    def tokens(self, table: Any) -> None:
        table.id()
        table.morphs("tokenable")
        table.string("name")
        table.string("token", 64).unique()
        table.text("abilities").nullable()
        table.timestamp("last_used_at").nullable()
        table.timestamp("expires_at").nullable()
        table.timestamps()
