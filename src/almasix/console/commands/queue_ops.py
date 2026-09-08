"""Queue operations — ``queue:restart``, ``queue:clear`` and ``queue:monitor``."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from almasix.console.command import Command
from almasix.console.confirmable import Confirmable
from almasix.queue.manager import QueueManager
from almasix.queue.restart import broadcast_restart, restart_store

#: The ``--max`` the signature declares, for callers that pass no options.
DEFAULT_BUSY_AT = 1000

#: Why a given driver has nothing to clear, when the reason is worth saying.
_CANNOT_CLEAR = {
    "sync": "it runs every job as it is dispatched, so none is ever left waiting",
}


class QueueOperation(Command):
    """Shared body: the queue manager, and opening a connection by name.

    Nothing here may be called ``connection``, ``queue`` or ``queues``: those are
    input names on these commands, and ``Command.run`` sets input as attributes.
    """

    def manager(self) -> QueueManager:
        return self.app.make(QueueManager)

    def open_connection(self, manager: QueueManager, name: str | None) -> tuple[str, Any] | None:
        """Resolve a named connection, or report why it could not be built."""
        resolved = str(name or manager.get_default_connection())
        try:
            return resolved, manager.connection(resolved)
        except KeyError:
            self.error(f"Queue connection [{resolved}] is not configured.")
        except ValueError as exc:
            # An unknown driver in config/queue.py.
            self.error(str(exc))
        return None

    def driver_of(self, connection: Any) -> str:
        """The driver name a connection was built from."""
        config = getattr(connection, "config", None) or {}
        return str(config.get("driver") or type(connection).__name__)

    def text_option(self, key: str, fallback: str) -> str | None:
        """An option's text, or ``None`` when what arrived cannot be one.

        The parser turns a bare ``--queue`` into ``True``, and a queue named
        "True" is not what anybody meant. ``fallback`` covers ``Artisan.call``,
        which passes the options it was given rather than the signature's.
        """
        value = self.option(key, fallback)
        if value is True or not str(value or "").strip():
            self.error(f"Invalid value for '--{key}': provide a value, e.g. --{key}={fallback}.")
            return None
        return str(value).strip()


class QueueRestartCommand(Command):
    signature = "queue:restart"
    description = "Ask every running worker to stop once it finishes its current job"

    def handle(self) -> int:
        try:
            stamp = broadcast_restart()
        except RuntimeError as exc:
            self.error(f"Cannot broadcast a restart: {exc}")
            return self.FAILURE

        self.warn_when_signal_cannot_travel()
        moment = datetime.fromtimestamp(stamp).isoformat(sep=" ", timespec="seconds")
        self.success("Broadcasting queue restart signal.")
        self.line(f"Workers started before {moment} will stop after their current job.")
        return self.SUCCESS

    def warn_when_signal_cannot_travel(self) -> None:
        """Say so when the signal was written somewhere no other process reads.

        The array store (and the null store built on it) lives inside this
        interpreter, so the timestamp is gone the moment ``smith`` exits.
        """
        from almasix.cache.drivers.array import ArrayStore
        from almasix.cache.helpers import get_manager

        if isinstance(restart_store().store, ArrayStore):
            self.warn(
                f"The [{get_manager().get_default_driver()}] cache store is private to this "
                "process, so no running worker can see this signal. Point CACHE_STORE at a "
                "shared store (file, database or redis) for queue:restart to reach them."
            )


class QueueClearCommand(Confirmable, QueueOperation):
    signature = (
        "queue:clear {connection? : Queue connection to clear (default: the configured default)} "
        "{--queue=default : Name of the queue to clear} "
        "{--force : Clear without asking, and clear in production}"
    )
    description = "Delete all of the jobs waiting on a queue"

    def handle(self) -> int:
        queue = self.text_option("queue", "default")
        if queue is None:
            return self.INVALID

        manager = self.manager()
        opened = self.open_connection(manager, self.argument("connection"))
        if opened is None:
            return self.FAILURE
        name, connection = opened

        clear = getattr(connection, "clear", None)
        if not callable(clear):
            driver = self.driver_of(connection)
            reason = _CANNOT_CLEAR.get(driver, "it has no way to delete jobs it never stored")
            self.error(f"Clearing is not supported on the [{driver}] queue driver — {reason}.")
            return self.FAILURE

        if not self.confirm_to_proceed(
            f"This deletes every job waiting on [{name}] queue [{queue}]."
        ):
            return self.FAILURE

        try:
            deleted = asyncio.run(clear(queue))
        except Exception as exc:  # noqa: BLE001 - the backing store is the user's to fix
            self.error(f"Could not clear [{name}] queue [{queue}]: {exc}")
            return self.FAILURE
        self.success(f"Cleared {deleted} job(s) from [{name}] queue [{queue}].")
        return self.SUCCESS


class QueueMonitorCommand(QueueOperation):
    signature = (
        "queue:monitor {queues : Comma-separated queues to size, each optionally connection:queue} "
        f"{{--max={DEFAULT_BUSY_AT} : Size at or above which a queue counts as busy}}"
    )
    description = "Show the size of each named queue, flagging the busy ones"

    def handle(self) -> int:
        raw_max = self.option("max", DEFAULT_BUSY_AT)
        try:
            maximum = int(str(raw_max))
        except (TypeError, ValueError):
            self.error(f"Invalid value for '--max': {raw_max!r} is not a valid integer.")
            return self.INVALID

        wanted = [part.strip() for part in str(self.argument("queues") or "").split(",")]
        wanted = [part for part in wanted if part]
        if not wanted:
            self.error("Name at least one queue, e.g. queue:monitor database:default.")
            return self.FAILURE

        plan = self.plan(wanted)
        rows = asyncio.run(self.measure(plan, maximum))
        self.table(["Connection", "Queue", "Size", "Status"], rows)
        return self.FAILURE if any(row[3] == "unreadable" for row in rows) else self.SUCCESS

    def plan(self, wanted: list[str]) -> list[dict[str, Any]]:
        """Turn ``connection:queue`` text into the connections to ask.

        A bare name is a queue on the default connection, as Laravel reads it.
        Each connection is opened once, so an unconfigured one is reported once.
        """
        manager = self.manager()
        opened: dict[str, Any] = {}
        entries: list[dict[str, Any]] = []
        for entry in wanted:
            if ":" in entry:
                name, queue = entry.split(":", 1)
            else:
                name, queue = manager.get_default_connection(), entry
            name, queue = name.strip(), queue.strip() or "default"
            if name not in opened:
                found = self.open_connection(manager, name)
                opened[name] = None if found is None else found[1]
            entries.append({"connection": name, "queue": queue, "object": opened[name]})
        return entries

    async def measure(self, plan: list[dict[str, Any]], maximum: int) -> list[list[Any]]:
        """Size every planned queue in one event loop, dispatching ``QueueBusy``."""
        rows: list[list[Any]] = []
        for entry in plan:
            connection = entry["object"]
            size_of = getattr(connection, "size", None) if connection is not None else None
            if not callable(size_of):
                if connection is not None:
                    self.error(
                        f"The [{self.driver_of(connection)}] queue driver cannot report a size."
                    )
                rows.append([entry["connection"], entry["queue"], "-", "unreadable"])
                continue
            try:
                size = int(await size_of(entry["queue"]) or 0)
            except Exception as exc:  # noqa: BLE001 - an unreachable store is not a crash
                self.error(
                    f"Could not size [{entry['connection']}] queue [{entry['queue']}]: {exc}"
                )
                rows.append([entry["connection"], entry["queue"], "-", "unreadable"])
                continue
            busy = size >= maximum
            rows.append([entry["connection"], entry["queue"], size, "BUSY" if busy else "OK"])
            if busy:
                self.report_busy(entry["connection"], entry["queue"], size)
        return rows

    def report_busy(self, connection: str, queue: str, size: int) -> None:
        """Dispatch ``QueueBusy`` so an application can page someone."""
        from almasix.events.facade import Event
        from almasix.queue.events import QueueBusy

        Event.dispatch(QueueBusy(connection=connection, queue=queue, size=size))
