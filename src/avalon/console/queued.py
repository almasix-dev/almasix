"""Queue job wrapper for ``Artisan.queue``.

Kept out of ``avalon.console.facade`` so importing the console does not pull in
the ORM-backed queue package (and its import cycle) at startup.
"""

from __future__ import annotations

from typing import Any

from avalon.queue.job import Job, ShouldQueue


class CallQueuedCommand(Job, ShouldQueue):
    """Runs a console command on a queue worker."""

    def __init__(
        self,
        command: str,
        parameters: dict[str, Any] | None = None,
        *,
        connection: str | None = None,
        queue: str | None = None,
    ) -> None:
        self.command = command
        self.parameters = dict(parameters or {})
        if connection is not None:
            self.connection = connection
        if queue is not None:
            self.queue = queue

    def handle(self) -> int:
        from avalon.console.facade import Artisan

        return Artisan.call(self.command, self.parameters, silent=True)
