"""Create the tables the queue stores its work in."""

from __future__ import annotations

from typing import Any

from almasix.orm.migration import Migration
from almasix.orm.schema import Schema


class CreateQueueTables(Migration):
    async def up(self) -> None:
        await Schema.create("jobs", self.jobs)
        await Schema.create("failed_jobs", self.failed_jobs)

    async def down(self) -> None:
        await Schema.drop_if_exists("failed_jobs")
        await Schema.drop_if_exists("jobs")

    def jobs(self, table: Any) -> None:
        # INTEGER primary key, not BigInteger: SQLite only autoincrements the former.
        table.id("id")
        table.string("queue")
        table.text("payload")
        table.integer("attempts").default(0)
        table.timestamp("reserved_at").nullable()
        table.timestamp("available_at")
        table.timestamp("created_at")

    def failed_jobs(self, table: Any) -> None:
        table.id("id")
        table.uuid("uuid")
        table.text("connection")
        table.text("queue")
        table.text("payload")
        table.text("exception")
        table.timestamp("failed_at")
