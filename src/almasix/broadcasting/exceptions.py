"""Broadcasting failures."""

from __future__ import annotations


class BroadcastException(RuntimeError):
    """A broadcaster could not deliver an event."""


class AccessDeniedException(RuntimeError):
    """A client asked to listen on a channel it may not listen on."""

    def __init__(self, channel: str = "", message: str = "") -> None:
        self.channel = channel
        super().__init__(message or f"Not authorized to join channel [{channel}].")
