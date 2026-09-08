"""Database queue driver — persists jobs for workers."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from almasix.queue.job import Job

if TYPE_CHECKING:
    from almasix.queue.manager import QueueManager


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class DatabaseQueue:
    """SQL-backed queue connection."""

    def __init__(
        self,
        app: Any | None,
        config: dict[str, Any],
        *,
        manager: QueueManager | None = None,
        connection_name: str = "database",
    ) -> None:
        self.app = app
        self.config = config
        self.manager = manager
        self.connection_name = connection_name
        self.table = str(config.get("table") or "jobs")
        # ``None`` is DB's word for the configured default connection, where
        # "default" is a connection name that almost no application defines.
        configured = config.get("connection")
        self.db_connection: str | None = str(configured) if configured else None

    async def push(self, job: Job) -> bool:
        from almasix.orm.facade import DB

        queue = job.queue_name()
        available_at = _utcnow() + timedelta(seconds=float(job.delay or 0))
        unique_id = job.unique_id()

        envelope = job.serialize()
        if unique_id:
            envelope["unique_id"] = unique_id
            unique_for = getattr(job, "unique_for", None) or job.__class__.unique_for
            if unique_for:
                envelope["unique_until"] = (
                    _utcnow() + timedelta(seconds=float(unique_for))
                ).isoformat()
        payload = json.dumps(envelope, default=str)

        if unique_id and (getattr(job, "unique_for", None) or job.__class__.unique_for):
            existing = await DB.select_one(
                f"SELECT id, payload FROM {self.table} WHERE queue = :queue "
                f"AND payload LIKE :needle LIMIT 1",
                {"queue": queue, "needle": f'%"unique_id": "{unique_id}"%'},
                connection=self.db_connection,
            )
            if existing:
                try:
                    prior = json.loads(existing["payload"])
                    until = prior.get("unique_until")
                    if until:
                        deadline = datetime.fromisoformat(str(until))
                        if deadline > _utcnow():
                            return False
                    else:
                        return False
                except Exception:
                    return False

        await DB.statement(
            f"""
            INSERT INTO {self.table}
                (queue, payload, attempts, reserved_at, available_at, created_at)
            VALUES
                (:queue, :payload, 0, NULL, :available_at, :created_at)
            """,
            {
                "queue": queue,
                "payload": payload,
                "available_at": available_at,
                "created_at": _utcnow(),
            },
            connection=self.db_connection,
        )
        return True

    async def pop(self, queue: str = "default") -> dict[str, Any] | None:
        from almasix.orm.facade import DB

        now = _utcnow()
        row = await DB.select_one(
            f"""
            SELECT id, queue, payload, attempts
            FROM {self.table}
            WHERE queue = :queue
              AND available_at <= :now
              AND reserved_at IS NULL
            ORDER BY id ASC
            LIMIT 1
            """,
            {"queue": queue, "now": now},
            connection=self.db_connection,
        )
        if row is None:
            return None

        reserved = await DB.statement(
            f"""
            UPDATE {self.table}
            SET reserved_at = :now
            WHERE id = :id AND reserved_at IS NULL
            """,
            {"id": row["id"], "now": now},
            connection=self.db_connection,
        )
        if reserved == 0:
            return None
        return dict(row)

    async def delete(self, job_id: int) -> None:
        from almasix.orm.facade import DB

        await DB.statement(
            f"DELETE FROM {self.table} WHERE id = :id",
            {"id": job_id},
            connection=self.db_connection,
        )

    async def release(self, job_id: int, *, delay: int = 0) -> None:
        from almasix.orm.facade import DB

        available_at = _utcnow() + timedelta(seconds=delay)
        await DB.statement(
            f"""
            UPDATE {self.table}
            SET reserved_at = NULL, available_at = :available_at, attempts = attempts + 1
            WHERE id = :id
            """,
            {"id": job_id, "available_at": available_at},
            connection=self.db_connection,
        )

    async def clear(self, queue: str = "default") -> int:
        """Delete every job on ``queue``, returning how many went (``queue:clear``).

        Reserved rows go too, as Laravel's does: a worker that finishes one
        afterwards simply deletes a row that is no longer there.
        """
        from almasix.orm.facade import DB

        deleted = await DB.statement(
            f"DELETE FROM {self.table} WHERE queue = :queue",
            {"queue": queue},
            connection=self.db_connection,
        )
        return int(deleted or 0)

    async def size(self, queue: str = "default") -> int:
        from almasix.orm.facade import DB

        row = await DB.select_one(
            f"""
            SELECT COUNT(*) AS total
            FROM {self.table}
            WHERE queue = :queue AND reserved_at IS NULL
            """,
            {"queue": queue},
            connection=self.db_connection,
        )
        return int((row or {}).get("total") or 0)

    async def restore_failed(self, failed_id: int) -> bool:
        from almasix.queue.failed import FailedJobRepository

        repo = FailedJobRepository(self.manager.failed_config() if self.manager else {})
        record = await repo.find(failed_id)
        if record is None:
            return False
        await self.push(Job.deserialize(json.loads(record["payload"])))
        await repo.delete(failed_id)
        return True

    async def restore_all_failed(self) -> int:
        from almasix.queue.failed import FailedJobRepository

        repo = FailedJobRepository(self.manager.failed_config() if self.manager else {})
        rows = await repo.all()
        count = 0
        for row in rows:
            if await self.restore_failed(int(row["id"])):
                count += 1
        return count

    def new_failed_uuid(self) -> str:
        return str(uuid4())
