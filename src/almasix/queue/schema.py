"""Queue table helpers — ``ensure_tables`` for jobs and failed_jobs."""

from __future__ import annotations

from typing import Any

from almasix.orm.schema import Schema


async def ensure_tables(connection: str | None = None) -> None:
    """Create ``jobs`` and ``failed_jobs`` when missing."""
    if not await Schema.has_table("jobs", connection=connection):
        await Schema.create("jobs", _define_jobs_table, connection=connection)
    if not await Schema.has_table("failed_jobs", connection=connection):
        await Schema.create("failed_jobs", _define_failed_jobs_table, connection=connection)


def _define_jobs_table(table: Any) -> None:
    # INTEGER PK for SQLite autoincrement compatibility (BigInteger skips AUTOINCREMENT).
    table.id("id")
    table.string("queue")
    table.text("payload")
    table.integer("attempts").default(0)
    table.timestamp("reserved_at").nullable()
    table.timestamp("available_at")
    table.timestamp("created_at")


def _define_failed_jobs_table(table: Any) -> None:
    table.id("id")
    table.uuid("uuid")
    table.text("connection")
    table.text("queue")
    table.text("payload")
    table.text("exception")
    table.timestamp("failed_at")
