"""Database cache store (``cache`` table) + atomic add / increment."""

from __future__ import annotations

import asyncio
import pickle
import time
from typing import Any


def _run(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Already in a loop — schedule on a dedicated thread.
    import concurrent.futures  # pragma: no cover

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:  # pragma: no cover
        return pool.submit(asyncio.run, coro).result()  # pragma: no cover


class DatabaseStore:
    """Persist cache rows via Articulate ``DB`` façade.

    ``add`` uses dialect insert-ignore (atomic). ``increment`` runs in a
    transaction. Locks use the ``cache_locks`` table (see ``DatabaseLock``).
    Tags are **not** supported (Laravel-honest).
    """

    supports_tags = False

    def __init__(
        self,
        *,
        table: str = "cache",
        lock_table: str = "cache_locks",
        connection: str | None = None,
    ) -> None:
        self.table = table
        self.lock_table = lock_table
        self.connection = connection

    def get(self, key: str) -> Any:
        return _run(self._aget(key))

    def put(self, key: str, value: Any, seconds: int | None) -> bool:
        return bool(_run(self._aput(key, value, seconds)))

    def forever(self, key: str, value: Any) -> bool:
        # Laravel uses a far-future TTL; NULL expiration is equivalent.
        return self.put(key, value, None)

    def forget(self, key: str) -> bool:
        return bool(_run(self._aforget(key)))

    def flush(self) -> bool:
        return bool(_run(self._aflush()))

    def add(self, key: str, value: Any, seconds: int | None = None) -> bool:
        return bool(_run(self._aadd(key, value, seconds)))

    def increment(self, key: str, amount: int = 1) -> int | bool:
        return _run(self._aincrement(key, amount))

    def decrement(self, key: str, amount: int = 1) -> int | bool:
        return self.increment(key, -amount)

    def lock(self, name: str, seconds: int | None = None, owner: str | None = None) -> Any:
        from almasix.cache.locks import DatabaseLock

        return DatabaseLock(
            connection=self.connection,
            table=self.lock_table,
            name=name,
            seconds=seconds,
            owner=owner,
        )

    def flush_locks(self) -> bool:
        return bool(_run(self._aflush_locks()))

    def restore_lock(self, name: str, owner: str) -> Any:
        return self.lock(name, seconds=None, owner=owner)

    async def _aget(self, key: str) -> Any:
        from almasix.orm.facade import DB

        rows = await DB.select(
            f"SELECT value, expiration FROM {self.table} WHERE key = :key LIMIT 1",
            {"key": key},
            connection=self.connection,
        )
        if not rows:
            return None
        row = rows[0]
        expiration = row.get("expiration")
        if expiration is not None and int(expiration) <= int(time.time()):
            await self._aforget(key)
            return None
        try:
            raw = row["value"]
            return pickle.loads(raw if isinstance(raw, (bytes, bytearray)) else bytes(raw))
        except Exception:
            await self._aforget(key)
            return None

    async def _aput(self, key: str, value: Any, seconds: int | None) -> bool:
        from almasix.orm.facade import DB

        payload = pickle.dumps(value, protocol=4)
        expiration = None if seconds is None else int(time.time()) + max(0, int(seconds))
        await DB.statement(
            f"DELETE FROM {self.table} WHERE key = :key",
            {"key": key},
            connection=self.connection,
        )
        await DB.statement(
            f"""
            INSERT INTO {self.table} (key, value, expiration)
            VALUES (:key, :value, :expiration)
            """,
            {"key": key, "value": payload, "expiration": expiration},
            connection=self.connection,
        )
        return True

    async def _aadd(self, key: str, value: Any, seconds: int | None) -> bool:
        """Atomic add — purge expired, then insert-ignore."""
        from almasix.orm.facade import DB

        if await self._aget(key) is not None:
            return False

        payload = pickle.dumps(value, protocol=4)
        expiration = None if seconds is None else int(time.time()) + max(0, int(seconds))
        dialect = DB.connection(self.connection).dialect
        params = {"key": key, "value": payload, "expiration": expiration}

        if dialect == "sqlite":
            affected = await DB.statement(
                f"""
                INSERT OR IGNORE INTO {self.table} (key, value, expiration)
                VALUES (:key, :value, :expiration)
                """,
                params,
                connection=self.connection,
            )
            return affected > 0
        if dialect in {"mysql", "mariadb"}:  # pragma: no cover
            affected = await DB.statement(
                f"""
                INSERT IGNORE INTO {self.table} (key, value, expiration)
                VALUES (:key, :value, :expiration)
                """,
                params,
                connection=self.connection,
            )
            return affected > 0
        # PostgreSQL / others — plain insert; integrity failure means not added.
        try:  # pragma: no cover
            await DB.statement(
                f"""
                INSERT INTO {self.table} (key, value, expiration)
                VALUES (:key, :value, :expiration)
                """,
                params,
                connection=self.connection,
            )
            return True
        except Exception:  # pragma: no cover
            return False

    async def _aincrement(self, key: str, amount: int) -> int | bool:
        from almasix.orm.facade import DB

        async with DB.transaction(self.connection):
            rows = await DB.select(
                f"SELECT value, expiration FROM {self.table} WHERE key = :key LIMIT 1",
                {"key": key},
                connection=self.connection,
            )
            now = int(time.time())
            if not rows:
                await self._aput(key, amount, None)
                return amount
            row = rows[0]
            expiration = row.get("expiration")
            if expiration is not None and int(expiration) <= now:
                await self._aforget(key)
                await self._aput(key, amount, None)
                return amount
            try:
                raw = row["value"]
                current = pickle.loads(raw if isinstance(raw, (bytes, bytearray)) else bytes(raw))
                next_value = int(current) + amount
            except (TypeError, ValueError, Exception):
                return False
            # Preserve remaining TTL
            ttl = None if expiration is None else max(0, int(expiration) - now)
            await self._aput(key, next_value, ttl)
            return next_value

    async def _aforget(self, key: str) -> bool:
        from almasix.orm.facade import DB

        await DB.statement(
            f"DELETE FROM {self.table} WHERE key = :key",
            {"key": key},
            connection=self.connection,
        )
        return True

    async def _aflush(self) -> bool:
        from almasix.orm.facade import DB

        await DB.statement(f"DELETE FROM {self.table}", connection=self.connection)
        return True

    async def _aflush_locks(self) -> bool:
        from almasix.orm.facade import DB

        await DB.statement(f"DELETE FROM {self.lock_table}", connection=self.connection)
        return True
