"""The database commands that are not migrations — ``db`` and ``db:wipe``."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from collections.abc import Mapping
from typing import Any

from almasix.console.command import Command
from almasix.console.confirmable import Confirmable
from almasix.orm.connection import _merge
from almasix.orm.facade import get_manager
from almasix.orm.schema import Schema


class DbCommand(Command):
    """Laravel's ``db`` — open the engine's own command-line client.

    Almasix does not reimplement a SQL shell; it hands you the one the engine
    ships, with the connection already filled in. If that client is not
    installed the command says which one it looked for rather than failing
    with "command not found".
    """

    signature = (
        "db {connection? : Connection to open (default: the configured default)} "
        "{--read : Connect to the read half of a split connection} "
        "{--write : Connect to the write half of a split connection} "
        "{--pooled : Use the pooled connection rather than the direct one}"
    )
    description = "Start a new database CLI session"

    def handle(self) -> int:
        manager = get_manager()
        name = str(self.argument("connection") or "").strip() or manager.default
        if not self.option("pooled"):
            name = manager.direct_name(name)

        try:
            definition = manager._definition(name)
        except Exception as exc:
            self.error(str(exc))
            return self.FAILURE

        if self.option("read"):
            definition = _merge(definition, definition.get("read"))
        elif self.option("write"):
            definition = _merge(definition, definition.get("write"))

        command = _client_command(definition)
        if command is None:
            driver = definition.get("driver", "unknown")
            self.error(f"Almasix has no command-line client for the {driver!r} driver.")
            return self.INVALID

        binary, arguments, environment = command
        found = shutil.which(binary)
        if found is None:
            self.error(f"{binary!r} is not installed, or not on PATH.")
            return self.FAILURE

        self.line(f"Connecting to [{name}] with {binary}.")
        # argv built from config, never a shell string.
        completed = subprocess.run(
            [found, *arguments],
            env={**os.environ, **environment},
            check=False,
        )
        return int(completed.returncode)


def _client_command(
    definition: Mapping[str, Any],
) -> tuple[str, list[str], dict[str, str]] | None:
    """The argv that opens this driver's client, and what it needs in the env."""
    driver = str(definition.get("driver", "")).lower()
    host = str(definition.get("host", "") or "")
    port = str(definition.get("port", "") or "")
    database = str(definition.get("database", "") or "")
    username = str(definition.get("username", "") or "")
    password = str(definition.get("password", "") or "")

    if driver in {"sqlite", "sqlite3"}:
        return "sqlite3", [database], {}
    if driver in {"mysql", "mariadb"}:
        arguments = ["--database", database]
        if host:
            arguments += ["--host", host]
        if port:
            arguments += ["--port", port]
        if username:
            arguments += ["--user", username]
        return "mysql", arguments, {"MYSQL_PWD": password} if password else {}
    if driver in {"postgresql", "postgres", "pgsql"}:
        arguments = ["--dbname", database]
        if host:
            arguments += ["--host", host]
        if port:
            arguments += ["--port", port]
        if username:
            arguments += ["--username", username]
        return "psql", arguments, {"PGPASSWORD": password} if password else {}
    if driver in {"mssql", "sqlsrv"}:
        server = f"{host},{port}" if port else host
        arguments = ["-S", server, "-d", database]
        if username:
            arguments += ["-U", username, "-P", password]
        return "sqlcmd", arguments, {}
    return None


class DbWipeCommand(Confirmable, Command):
    """Drop every table, the way ``migrate:fresh`` clears the way for itself.

    ``--drop-views`` and ``--drop-types`` are declared so the refusal is a
    sentence rather than "no such option": Almasix's schema layer knows about
    tables only, and a flag that quietly did nothing would leave the views
    behind while reporting success.
    """

    signature = (
        "db:wipe {--database= : Connection to wipe (default: the configured default)} "
        "{--drop-views : Also drop views — Almasix's schema layer cannot} "
        "{--drop-types : Also drop custom types — Almasix's schema layer cannot} "
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
        except Exception as exc:
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
        asked = [
            flag for flag in ("drop-views", "drop-types") if self.option(flag.replace("-", "_"))
        ]
        if not asked:
            return None
        flags = " and ".join(f"--{flag}" for flag in asked)
        self.error(
            f"{flags} cannot be honoured: Almasix's schema layer drops tables only. "
            "Nothing was dropped — re-run without it, or drop them by hand first."
        )
        return self.INVALID

    async def wipe(self, connection: str | None) -> list[str]:
        """Drop every table, through the same pieces ``Migrator.fresh()`` uses."""
        names = await Schema.table_names(connection=connection)
        for name in names:
            await Schema.drop_if_exists(name, connection=connection)
        return names
