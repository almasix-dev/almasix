"""Where `ShouldBroadcast` used to live.

The marker moved to `almasix.broadcasting` when broadcasting shipped; events
that imported it from here keep working.
"""

from __future__ import annotations

from almasix.broadcasting.events import (
    InteractsWithBroadcasting,
    InteractsWithSockets,
    ShouldBroadcast,
    ShouldBroadcastAfterCommit,
    ShouldBroadcastNow,
)

__all__ = [
    "InteractsWithBroadcasting",
    "InteractsWithSockets",
    "ShouldBroadcast",
    "ShouldBroadcastAfterCommit",
    "ShouldBroadcastNow",
]
