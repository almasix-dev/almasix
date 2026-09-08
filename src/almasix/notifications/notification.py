"""Notification base class."""

from __future__ import annotations

from typing import Any, ClassVar


class ShouldQueue:
    """Marker — notification is queued when a queue is available."""


class Notification:
    """Laravel-shaped notification: ``via`` + channel builders."""

    queue: ClassVar[str | bool] = False
    connection: ClassVar[str | None] = None
    delay: ClassVar[int | float] = 0

    def via(self, notifiable: Any) -> list[str]:
        """Return channel names, e.g. ``['mail', 'database']``."""
        del notifiable
        return ["mail"]

    def to_mail(self, notifiable: Any) -> Any:
        """Return a ``Mailable`` or mail payload dict."""
        raise NotImplementedError(f"{type(self).__name__}.to_mail() is not implemented")

    def to_database(self, notifiable: Any) -> dict[str, Any]:
        """Return JSON-serializable payload for the notifications table."""
        del notifiable
        return {"message": str(self)}

    def to_array(self, notifiable: Any) -> dict[str, Any]:
        """Payload for array/log test channels."""
        try:
            return self.to_database(notifiable)
        except Exception:
            return {"notification": type(self).__name__}

    def should_queue(self) -> bool:
        if isinstance(self, ShouldQueue):
            return True
        return self.queue is True or (isinstance(self.queue, str) and bool(self.queue))

    def queue_name(self) -> str:
        if isinstance(self.queue, str) and self.queue:
            return self.queue
        return "default"
