"""The database commands that are not migrations — ``db:wipe``."""

from __future__ import annotations

import asyncio

from avalon.console.command import Command
from avalon.console.confirmable import Confirmable
from avalon.orm.schema import Schema


class DbWipeCommand(Confirmable, Command):
    """Drop every table, the way ``migrate:fresh`` clears the way for itself.

    ``--drop-views`` and ``--drop-types`` are declared so the refusal is a
    sentence rather than "no such option": Avalon's schema layer knows about
    tables only, and a flag that quietly did nothing would leave the views
    behind while reporting success.
    """

    signature = (
        "db:wipe {--database= : Connection to wipe (default: the configured default)} "
        "{--drop-views : Also drop views — Avalon's schema layer cannot} "
        "{--drop-types : Also drop custom types — Avalon's schema layer cannot} "
        "{--force : Wipe without asking, and allow it in production}"
    )
    description = "Drop all tables from the database"

    def handle(self) -> int:
        unsupported = self.refuse_unsupported()
        if unsupported is not None:
            return unsupported

        given = self.option("database")
        if given is True:
            self.error(
                "Invalid value for '--database': provide a connection name, e.g. --database=sqlite."
            )
            return self.INVALID
        connection = str(given or "").strip() or None

        if not self.confirm_to_proceed(
            f"This drops every table in the [{connection or 'default'}] database."
        ):
            return self.FAILURE

        try:
            dropped = asyncio.run(self.wipe(connection))
        except Exception as exc:  # noqa: BLE001 - the database is the user's to fix
            self.error(str(exc))
            return self.FAILURE

        if not dropped:
            self.line("Nothing to drop.")
            return self.SUCCESS
        for name in dropped:
            self.line(f"Dropped: {name}")
        self.success(f"Dropped {len(dropped)} table(s).")
        return self.SUCCESS

    def refuse_unsupported(self) -> int | None:
        """Stop before dropping anything when asked for something we cannot do."""
        asked = [flag for flag in ("drop-views", "drop-types") if self.option(flag.replace("-", "_"))]
        if not asked:
            return None
        flags = " and ".join(f"--{flag}" for flag in asked)
        self.error(
            f"{flags} cannot be honoured: Avalon's schema layer drops tables only. "
            "Nothing was dropped — re-run without it, or drop them by hand first."
        )
        return self.INVALID

    async def wipe(self, connection: str | None) -> list[str]:
        """Drop every table, through the same pieces ``Migrator.fresh()`` uses."""
        names = await Schema.table_names(connection=connection)
        for name in names:
            await Schema.drop_if_exists(name, connection=connection)
        return names
