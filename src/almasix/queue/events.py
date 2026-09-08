"""Queue events — dispatched through the application event dispatcher."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class QueueBusy:
    """Fired by ``queue:monitor`` for a queue at or above its ``--max`` size.

    Listen for it to page someone when work piles up faster than the workers
    drain it (Laravel's ``Illuminate\\Queue\\Events\\QueueBusy``).
    """

    connection: str
    queue: str
    size: int
