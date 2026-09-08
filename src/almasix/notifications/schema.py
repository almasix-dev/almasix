"""Create the ``notifications`` table when missing."""

from __future__ import annotations

from typing import Any

from almasix.orm.schema import Schema


async def ensure_tables(connection: str | None = None) -> None:
    if not await Schema.has_table("notifications", connection=connection):
        await Schema.create("notifications", _define_notifications, connection=connection)


def _define_notifications(table: Any) -> None:
    table.uuid("id").primary()
    table.string("type")
    table.string("notifiable_type")
    table.string("notifiable_id")
    table.text("data")
    table.timestamp("read_at").nullable()
    table.timestamps()
    table.index(["notifiable_type", "notifiable_id"])
