"""Serializable queued notification delivery."""

from __future__ import annotations

from typing import Any

from almasix.queue.job import Job, ShouldQueue


class SendQueuedNotification(ShouldQueue, Job):
    """Reconstruct notifiable + notification and deliver on the worker."""

    queue = "default"

    def __init__(
        self,
        *,
        notifiable_type: str,
        notifiable_id: Any,
        notification_class: str,
        notification_data: dict[str, Any] | None = None,
        channels: list[str] | None = None,
        queue_name: str = "default",
    ) -> None:
        self.notifiable_type = notifiable_type
        self.notifiable_id = notifiable_id
        self.notification_class = notification_class
        self.notification_data = notification_data or {}
        self.channels = channels
        self.queue = queue_name

    async def handle(self) -> list[Any]:
        from almasix.notifications.sender import NotificationSender

        notifiable = await resolve_notifiable(self.notifiable_type, self.notifiable_id)
        notification = resolve_notification(self.notification_class, self.notification_data)
        return await NotificationSender().send_now(
            notifiable,
            notification,
            channels=self.channels,
        )


def resolve_notification(class_path: str, data: dict[str, Any]) -> Any:
    cls = _import_class(class_path)
    try:
        instance = cls(**data) if data else cls()
    except TypeError:
        instance = cls()
        instance.__dict__.update(data)
    return instance


async def resolve_notifiable(class_path: str, key: Any) -> Any:
    cls = _import_class(class_path)
    finder = getattr(cls, "find", None)
    if callable(finder):
        result = finder(key)
        if hasattr(result, "__await__"):
            result = await result  # type: ignore[misc]
        if result is not None:
            return result
    # Fallback for plain objects used in tests.
    instance = object.__new__(cls)
    if hasattr(instance, "__dict__"):
        instance.__dict__.setdefault("id", key)
        if hasattr(instance, "set_attribute"):
            pass
    return instance


def _import_class(path: str) -> type:
    module_name, _, qualname = path.rpartition(".")
    if not module_name:
        raise ValueError(f"Invalid class path: {path!r}")
    import importlib

    module = importlib.import_module(module_name)
    obj: Any = module
    for part in qualname.split("."):
        obj = getattr(obj, part)
    if not isinstance(obj, type):
        raise TypeError(f"{path!r} is not a class")
    return obj
