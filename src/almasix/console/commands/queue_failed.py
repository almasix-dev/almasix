"""Failed job commands — reading the store, replaying from it, and emptying it.

``queue:failed`` and ``queue:retry`` look at what failed and put it back;
``queue:flush``, ``queue:forget`` and ``queue:prune-failed`` are the
maintenance side, which deletes.
"""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Coroutine
from typing import Any, TypeVar

from sqlalchemy.exc import SQLAlchemyError

from almasix.console.command import Command
from almasix.console.confirmable import Confirmable
from almasix.queue.connections.database import DatabaseQueue
from almasix.queue.failed import FailedJobRepository
from almasix.queue.manager import QueueManager

T = TypeVar("T")

#: The window ``queue:prune-failed`` keeps when it is given no ``--hours``.
DEFAULT_RETENTION_HOURS = 24


class FailedJobCommand(Command):
    """Shared body: the failed job store, and reading ``--hours`` off the input."""

    def repository(self) -> FailedJobRepository:
        return FailedJobRepository(self.app.make(QueueManager).failed_config())

    def read_store(self, work: Coroutine[Any, Any, T]) -> T:
        """Run one store operation, naming a missing table instead of raising at it.

        Nothing creates the failed jobs table for an application, so the first
        thing any of these commands does in a fresh app is query a table that
        is not there. That is worth a sentence, not a database traceback.
        """
        repository = self.repository()
        try:
            return asyncio.run(work)
        except SQLAlchemyError as exc:
            if repository.table not in str(exc):
                raise
            self.fail(
                f"The {repository.table} table does not exist. "
                f"Create it with a migration, then run smith migrate."
            )
            raise  # pragma: no cover - fail() always raises

    def retention_hours(self) -> float | None | bool:
        """``--hours`` as a number, ``None`` when absent, ``False`` when unusable.

        The parser turns a bare ``--hours`` into ``True``, and a window of
        "True" hours is not what anybody meant. A negative or infinite window
        puts the cutoff somewhere no timestamp can be compared against.
        """
        value = self.option("hours")
        if value is None:
            return None
        if value is True or not str(value).strip():
            self.error("Invalid value for '--hours': provide a number, e.g. --hours=24.")
            return False
        try:
            hours = float(str(value))
        except ValueError:
            self.error(f"Invalid value for '--hours': {value!r} is not a valid number.")
            return False
        if not math.isfinite(hours) or hours < 0:
            self.error(f"Invalid value for '--hours': {value!r} is not a length of time.")
            return False
        return hours


class QueueFailedCommand(FailedJobCommand):
    signature = "queue:failed {--limit=10}"
    description = "List failed queue jobs"

    def handle(self) -> int:
        repo = self.repository()
        limit = int(self.option("limit") or 10)
        rows = self.read_store(repo.all(limit=limit))
        if not rows:
            self.info("No failed jobs.")
            return 0
        table_rows = []
        for row in rows:
            payload = json.loads(row.get("payload") or "{}")
            job_class = payload.get("class", "?")
            table_rows.append(
                [
                    row.get("id"),
                    row.get("connection"),
                    row.get("queue"),
                    job_class,
                    str(row.get("failed_at") or "")[:19],
                ]
            )
        self.table(["ID", "Connection", "Queue", "Job", "Failed At"], table_rows)
        return 0


class QueueRetryCommand(FailedJobCommand):
    signature = "queue:retry {id?} {--all}"
    description = "Retry a failed queue job"

    def handle(self) -> int:
        manager = self.app.make(QueueManager)
        try:
            connection = manager.connection("database")
        except KeyError:
            self.error("Retry requires a database queue connection.")
            return 1
        if not isinstance(connection, DatabaseQueue):
            self.error("Retry requires a database queue connection.")
            return 1

        retry_all = bool(self.option("all"))
        failed_id = self.argument("id")

        async def _retry() -> int:
            if retry_all:
                count = await connection.restore_all_failed()
                return count
            if failed_id is None:
                return -1
            restored = await connection.restore_failed(int(failed_id))
            return 1 if restored else 0

        result = self.read_store(_retry())
        if result == -1:
            self.error("Provide a failed job id or use --all.")
            return 1
        if result == 0:
            self.warn("Failed job not found or could not be restored.")
            return 1
        self.success(f"Retried {result} failed job(s).")
        return 0


class QueueFlushCommand(Confirmable, FailedJobCommand):
    """Laravel's ``queue:flush`` — empty the failed job store.

    Unlike Laravel's, this asks before it deletes. A flushed job cannot be
    retried afterwards, and Almasix's confirmation guard covers every command
    that deletes jobs — ``--force`` is the way past it, as it is for
    ``queue:clear``.
    """

    signature = (
        "queue:flush {--hours= : Only delete jobs that failed more than this many hours ago} "
        "{--force : Flush without asking, and flush in production}"
    )
    description = "Delete all of the failed queue jobs"

    def handle(self) -> int:
        hours = self.retention_hours()
        if hours is False:
            return self.INVALID

        repository = self.repository()
        if not self.confirm_to_proceed(f"This deletes {self.scope(hours)}."):
            return self.FAILURE

        if hours is None:
            deleted = self.read_store(repository.flush())
        else:
            deleted = self.read_store(repository.prune(repository.cutoff(hours)))
        self.success(f"Deleted {deleted} failed job(s).")
        return self.SUCCESS

    def scope(self, hours: float | None) -> str:
        """What the confirmation says is about to go."""
        if hours is None:
            return "every failed job"
        return f"every job that failed more than {hours:g} hour(s) ago"


class QueueForgetCommand(FailedJobCommand):
    """Laravel's ``queue:forget`` — delete one failed job by ID."""

    signature = "queue:forget {id : The failed job ID, as listed by queue:failed}"
    description = "Delete a failed queue job"

    def handle(self) -> int:
        given = self.argument("id")
        try:
            failed_id = int(str(given))
        except ValueError:
            self.error(f"Invalid failed job ID: {given!r} is not a valid integer.")
            return self.INVALID

        if not self.read_store(self.repository().delete(failed_id)):
            self.warn(f"No failed job matches ID [{failed_id}].")
            return self.FAILURE
        self.success(f"Deleted failed job [{failed_id}].")
        return self.SUCCESS


class QueuePruneFailedCommand(FailedJobCommand):
    """Laravel's ``queue:prune-failed`` — trim the store to a retention window.

    This is the unattended sibling of ``queue:flush``: it is made to be
    scheduled, so it never stops to ask, and it only ever deletes what has
    already aged out of the window.
    """

    signature = (
        f"queue:prune-failed {{--hours={DEFAULT_RETENTION_HOURS} : "
        "Delete failed jobs older than this many hours}"
    )
    description = "Prune stale entries from the failed jobs table"

    def handle(self) -> int:
        hours = self.retention_hours()
        if hours is False:
            return self.INVALID
        # ``Smith.call`` passes the options it was given, not the signature's.
        window = DEFAULT_RETENTION_HOURS if hours is None else hours

        repository = self.repository()
        pruned = self.read_store(repository.prune(repository.cutoff(window)))
        if not pruned:
            self.info(f"No failed jobs older than {window:g} hour(s) to prune.")
            return self.SUCCESS
        self.success(f"Pruned {pruned} failed job(s) older than {window:g} hour(s).")
        return self.SUCCESS
