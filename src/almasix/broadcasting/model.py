"""Model broadcasting — a row changes, the browser hears about it.

Mix `BroadcastsEvents` into a model, say which channels each change goes on,
and creates, updates, trashes, restores and deletes broadcast themselves.
"""

from __future__ import annotations

from typing import Any, ClassVar

from almasix.broadcasting.channels import channel_names
from almasix.broadcasting.events import ShouldBroadcast, ShouldBroadcastNow

#: The model lifecycle changes worth telling a browser about.
BROADCAST_EVENTS = ("created", "updated", "trashed", "restored", "deleted")


class BroadcastableModelEvent(ShouldBroadcast):
    """The event a model broadcasts on its own behalf.

    Its name is the model and the change — `PostUpdated` — and its payload is
    the model, unless the model says otherwise in `broadcast_with()`.
    """

    def __init__(self, model: Any, event: str, channels: list[str]) -> None:
        self.model = model
        self.event = event
        self._channels = channels
        self.socket = None
        self.broadcast_queue = getattr(model, "broadcast_queue", None)
        self.broadcast_connection = getattr(model, "broadcast_connection", None)

    def broadcast_on(self) -> list[str]:
        return list(self._channels)

    def broadcast_as(self) -> str:
        alias = getattr(self.model, "broadcast_as", None)
        if callable(alias):
            named = alias(self.event)
            if named:
                return str(named)
        return f"{type(self.model).__name__}{self.event.capitalize()}"

    def broadcast_with(self) -> dict[str, Any]:
        payload = getattr(self.model, "broadcast_with", None)
        if callable(payload):
            explicit = payload(self.event)
            if explicit is not None:
                return dict(explicit)
        return {"model": self.model.to_dict()}

    def broadcast_connections(self) -> list[str | None]:
        return [self.broadcast_connection]


class BroadcastableModelEventNow(BroadcastableModelEvent, ShouldBroadcastNow):
    """The same event, sent during the write instead of through the queue."""


class BroadcastsEvents:
    """Mixin: model writes broadcast themselves.

    Mix in **before** `Model` so the metaclass boots it::

        class Post(BroadcastsEvents, Model):
            def broadcast_on(self, event: str):
                return [self, self.author]

    `broadcast_on()` is asked for every change and may return nothing for the
    ones that should stay quiet — returning `[]` for `deleted` means deletes
    are not broadcast. Returning the model itself means its own private
    channel, the way Laravel's model channels work.
    """

    #: Set on a model to send during the write rather than through the queue.
    broadcasts_now: ClassVar[bool] = False

    @staticmethod
    def boot_broadcasts_events(cls: Any) -> None:
        for event in BROADCAST_EVENTS:
            cls.listen(*_listener(cls, event))

    def broadcast_on(self, event: str) -> Any:
        """The channels a change of this kind goes out on."""
        raise NotImplementedError(
            f"{type(self).__name__} broadcasts its events but does not implement "
            f"broadcast_on(event). Return the channels for [{event}], or [] to stay quiet."
        )

    def new_broadcastable_event(self, event: str) -> BroadcastableModelEvent | None:
        """The event object for a change, or `None` when there is nowhere to send it."""
        names = channel_names(self.broadcast_on(event))
        if not names:
            return None
        factory = (
            BroadcastableModelEventNow
            if getattr(self, "broadcasts_now", False)
            else BroadcastableModelEvent
        )
        return factory(self, event, names)

    def broadcast_change(self, event: str) -> None:
        """Broadcast one change now — what the lifecycle listeners call."""
        broadcastable = self.new_broadcastable_event(event)
        if broadcastable is None:
            return
        from almasix.broadcasting.jobs import queue_broadcast

        queue_broadcast(broadcastable)


class BroadcastsEventsAfterCommit(BroadcastsEvents):
    """`BroadcastsEvents`, held until the surrounding transaction commits.

    Without a transaction it behaves identically; inside one, the broadcast
    waits so no browser learns about a row that gets rolled back.
    """

    @staticmethod
    def boot_broadcasts_events_after_commit(cls: Any) -> None:
        # The metaclass boots a trait by its own name, and only for direct
        # bases — inheriting the listeners is not the same as registering them.
        BroadcastsEvents.boot_broadcasts_events(cls)

    def broadcast_change(self, event: str) -> None:
        broadcastable = self.new_broadcastable_event(event)
        if broadcastable is None:
            return
        from almasix.broadcasting.jobs import queue_broadcast
        from almasix.orm.facade import get_manager

        connection = get_manager().connection(type(self).connection)
        connection.after_commit(lambda: queue_broadcast(broadcastable))


def _listener(cls: Any, event: str) -> tuple[str, Any]:
    """The model event to listen for, and what to do when it fires.

    `trashed` and `deleted` are the same model event: a soft delete leaves the
    row (and the instance) in existence, a hard delete does not.
    """
    del cls

    if event == "trashed":

        def on_trashed(model: Any) -> None:
            if getattr(model, "_soft_deletes", False) and model._exists:
                model.broadcast_change("trashed")

        return "deleted", on_trashed

    if event == "deleted":

        def on_deleted(model: Any) -> None:
            if not (getattr(model, "_soft_deletes", False) and model._exists):
                model.broadcast_change("deleted")

        return "deleted", on_deleted

    def on_change(model: Any, name: str = event) -> None:
        model.broadcast_change(name)

    return event, on_change
