"""Queue worker commands — ``queue:work`` and ``queue:listen``."""

from __future__ import annotations

import asyncio

from avalon.console.command import Command
from avalon.queue.manager import QueueManager
from avalon.queue.worker import Worker


class QueueWorkCommand(Command):
    signature = "queue:work {connection?} {--queue=default} {--once} {--sleep=1}"
    description = "Process the next job on a queue"

    def handle(self) -> int:
        connection = self.argument("connection")
        queue = str(self.option("queue") or "default")
        once = bool(self.option("once"))
        sleep = float(self.option("sleep") or 1)
        manager = self.app.make(QueueManager)
        worker = Worker(manager)
        processed = asyncio.run(
            worker.run(connection, queue=queue, once=once, sleep=sleep, max_jobs=1 if once else None)
        )
        if once and processed == 0:
            self.comment("No jobs available.")
        elif processed:
            self.info(f"Processed {processed} job(s).")
        if worker.stopped_for_restart:
            self.comment("Stopping worker: queue:restart was broadcast.")
        return 0


class QueueListenCommand(Command):
    signature = "queue:listen {connection?} {--queue=default} {--sleep=1}"
    description = "Listen to a given queue (continuous worker loop)"

    def handle(self) -> int:
        connection = self.argument("connection")
        queue = str(self.option("queue") or "default")
        sleep = float(self.option("sleep") or 1)
        manager = self.app.make(QueueManager)
        worker = Worker(manager)
        self.info(f"Listening on queue [{queue}]...")
        try:
            asyncio.run(worker.run(connection, queue=queue, sleep=sleep))
        except KeyboardInterrupt:
            self.comment("Stopping listener.")
        else:
            # A listener has no job limit, so the loop only ever returns to say
            # that a restart was broadcast.
            self.comment("Stopping listener: queue:restart was broadcast.")
        return 0
