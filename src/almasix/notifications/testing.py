"""Notifications under test — record instead of deliver, then assert."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from almasix.notifications.sender import NotificationSender


@dataclass
class RecordedNotification:
    """One notification that would have been delivered."""

    notification: Any
    notifiable: Any
    channels: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return type(self.notification).__name__


class FakeNotifications(NotificationSender):
    """A sender that remembers who would have been told what.

    Installed by `fake_notifications()`. No mail is built, no row is written,
    and no channel is asked for anything.
    """

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[RecordedNotification] = []

    async def send(self, notifiable: Any, notification: Any) -> list[Any]:
        return await self.send_now(notifiable, notification)

    async def send_now(
        self,
        notifiable: Any,
        notification: Any,
        *,
        channels: Sequence[str] | None = None,
    ) -> list[Any]:
        names = list(channels or notification.via(notifiable))
        self.sent.append(
            RecordedNotification(notification=notification, notifiable=notifiable, channels=names)
        )
        return []

    # --- assertions ------------------------------------------------------------

    def recorded(
        self,
        notification: type | str | None = None,
        callback: Callable[..., bool] | None = None,
    ) -> list[RecordedNotification]:
        found = [record for record in self.sent if _matches(record, notification)]
        if callback is None:
            return found
        return [record for record in found if _call(callback, record)]

    def assert_sent_to(
        self,
        notifiable: Any,
        notification: type | str,
        callback: Callable[..., bool] | None = None,
    ) -> None:
        for record in self.recorded(notification, callback):
            if _same(record.notifiable, notifiable):
                return
        raise AssertionError(
            f"[{_name(notification)}] was not sent to {_describe(notifiable)}. Sent: {self._names()}."
        )

    def assert_not_sent_to(self, notifiable: Any, notification: type | str) -> None:
        for record in self.recorded(notification):
            if _same(record.notifiable, notifiable):
                raise AssertionError(
                    f"[{_name(notification)}] was sent to {_describe(notifiable)}, and should not have been."
                )

    def assert_sent_times(self, notification: type | str, times: int = 1) -> None:
        found = len(self.recorded(notification))
        if found != times:
            raise AssertionError(
                f"Expected [{_name(notification)}] {times} time(s); it was sent {found}."
            )

    def assert_sent_on_channel(self, notification: type | str, channel: str) -> None:
        for record in self.recorded(notification):
            if channel in record.channels:
                return
        raise AssertionError(f"[{_name(notification)}] never went out over [{channel}].")

    def assert_nothing_sent(self) -> None:
        if self.sent:
            raise AssertionError(f"Expected no notifications; got: {self._names()}.")

    def assert_count(self, count: int) -> None:
        if len(self.sent) != count:
            raise AssertionError(f"Expected {count} notification(s); got {len(self.sent)}.")

    def flush(self) -> None:
        self.sent.clear()

    def _names(self) -> str:
        return ", ".join(record.name for record in self.sent) or "nothing"

    def __repr__(self) -> str:
        return f"FakeNotifications({len(self.sent)} sent)"


def fake_notifications() -> FakeNotifications:
    """Swap the sender for one that records (Laravel `Notification::fake()`)."""
    from almasix.notifications.helpers import set_sender

    fake = FakeNotifications()
    set_sender(fake)
    return fake


def _name(notification: type | str) -> str:
    return notification if isinstance(notification, str) else notification.__name__


def _matches(record: RecordedNotification, notification: type | str | None) -> bool:
    if notification is None:
        return True
    if isinstance(notification, str):
        return record.name == notification
    return isinstance(record.notification, notification)


def _call(callback: Callable[..., bool], record: RecordedNotification) -> bool:
    """A predicate may take the notification, or it and the notifiable."""
    from almasix.support.arity import accepts_two_arguments

    if accepts_two_arguments(callback):
        return bool(callback(record.notification, record.notifiable))
    return bool(callback(record.notification))


def _same(left: Any, right: Any) -> bool:
    if left is right:
        return True
    left_key = getattr(left, "get_key", None)
    right_key = getattr(right, "get_key", None)
    if callable(left_key) and callable(right_key) and type(left) is type(right):
        return left_key() == right_key()
    return left == right


def _describe(notifiable: Any) -> str:
    key = getattr(notifiable, "get_key", None)
    if callable(key):
        return f"[{type(notifiable).__name__} {key()}]"
    return f"[{notifiable}]"
