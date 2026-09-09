"""``*:table`` — migrations for the tables the framework itself reads.

A scaffolded application already has users, sessions, cache, and the queue
(M32 ships those migrations). These commands are for the application that did
not scaffold them, or dropped them, or switched a driver later: ``cache:table``
after moving the cache store to ``database``, ``notifications:table`` the first
time a notification is stored rather than mailed.

Each writes the same stub the scaffold does, so the schema cannot drift from
what the driver expects.
"""

from __future__ import annotations

from pathlib import Path

from almasix.console.command import Command
from almasix.orm.migration import MigrationError, make_migration


class TableMigrationCommand(Command):
    """Shared body: render one named stub into ``database/migrations``."""

    #: The stub to render, and the slug the file is named after.
    stub = ""
    slug = ""
    #: The table the stub's ``table`` placeholder means.
    table = ""
    #: What the migration creates, for the line printed afterwards.
    creates = ""
    boots_application = False

    def handle(self) -> int:
        root = Path.cwd()
        try:
            path = make_migration(
                self.slug,
                root / "database" / "migrations",
                table=self.table,
                base_path=root,
                stub=self.stub,
            )
        except MigrationError as exc:  # pragma: no cover - the slug is a constant
            self.error(str(exc))
            return self.FAILURE
        self.success(f"Migration created: {path.relative_to(root)}")
        self.line(f"  creates {self.creates}")
        return self.SUCCESS


class CacheTableCommand(TableMigrationCommand):
    signature = "cache:table"
    description = "Create a migration for the cache database tables"
    stub = "migration.cache.stub"
    slug = "create_cache_table"
    table = "cache"
    creates = "cache, cache_locks"


class QueueTableCommand(TableMigrationCommand):
    signature = "queue:table"
    description = "Create a migration for the queue jobs table"
    stub = "migration.jobs.stub"
    slug = "create_jobs_table"
    table = "jobs"
    creates = "jobs"


class QueueFailedTableCommand(TableMigrationCommand):
    signature = "queue:failed-table"
    description = "Create a migration for the failed queue jobs table"
    stub = "migration.failed_jobs.stub"
    slug = "create_failed_jobs_table"
    table = "failed_jobs"
    creates = "failed_jobs"


class SessionTableCommand(TableMigrationCommand):
    signature = "session:table"
    description = "Create a migration for the session database table"
    stub = "migration.sessions.stub"
    slug = "create_sessions_table"
    table = "sessions"
    creates = "sessions"


class NotificationsTableCommand(TableMigrationCommand):
    signature = "notifications:table"
    description = "Create a migration for the notifications table"
    stub = "migration.notifications.stub"
    slug = "create_notifications_table"
    table = "notifications"
    creates = "notifications"
