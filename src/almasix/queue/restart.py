"""The ``queue:restart`` signal — a timestamp workers watch in the cache.

Laravel restarts workers through the cache rather than through an OS signal: a
worker reads the timestamp when it boots and compares it on every pass of its
loop, so a deploy can ask for a restart without knowing where the workers run.
The comparison happens between jobs, which is what lets a worker finish the job
in hand before it exits.
"""

from __future__ import annotations

import time
from typing import Any

#: The cache key holding the last restart broadcast.
RESTART_KEY = "almasix:queue:restart"


def restart_store() -> Any:
    """The cache repository the signal lives in.

    Raises ``RuntimeError`` when the application has no cache. ``queue:restart``
    reports that; a worker reads it as "nobody has asked for a restart".
    """
    from almasix.cache.helpers import get_manager

    return get_manager().store()


def broadcast_restart(timestamp: float | None = None) -> float:
    """Ask every running worker to stop after its current job."""
    value = float(timestamp if timestamp is not None else time.time())
    restart_store().forever(RESTART_KEY, value)
    return value


def last_restart() -> float | None:
    """The last broadcast, or ``None`` when there is none — or no cache at all."""
    try:
        raw = restart_store().get(RESTART_KEY)
    except Exception:  # noqa: BLE001 - a worker without a cache simply never restarts
        return None
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        # Something else owns the key. Restarting on it would be a guess.
        return None
