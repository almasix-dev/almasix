"""Create the courier_messages table."""

from __future__ import annotations

from typing import Any

from almasix.orm import Migration, Schema


class CreateCourierMessagesTable(Migration):
    async def up(self) -> None:
        await Schema.create("courier_messages", self.define)

    async def down(self) -> None:
        await Schema.drop_if_exists("courier_messages")

    def define(self, table: Any) -> None:
        table.id()
        table.string("body")
        table.timestamps()
