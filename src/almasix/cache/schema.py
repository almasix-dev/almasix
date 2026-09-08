"""Ensure database cache + lock tables exist."""

from __future__ import annotations

CACHE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS cache (
    key VARCHAR(255) PRIMARY KEY NOT NULL,
    value BLOB NOT NULL,
    expiration INTEGER NULL
)
"""

CACHE_LOCKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS cache_locks (
    key VARCHAR(255) PRIMARY KEY NOT NULL,
    owner VARCHAR(255) NOT NULL,
    expiration INTEGER NOT NULL
)
"""


async def ensure_cache_table(connection: str | None = None) -> None:
    from almasix.orm.facade import DB

    await DB.statement(CACHE_TABLE_SQL, connection=connection)
    await DB.statement(CACHE_LOCKS_TABLE_SQL, connection=connection)


def ensure_cache_table_sync(connection: str | None = None) -> None:
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(ensure_cache_table(connection))
        return
    import concurrent.futures  # pragma: no cover

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:  # pragma: no cover
        pool.submit(asyncio.run, ensure_cache_table(connection)).result()  # pragma: no cover
