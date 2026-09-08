"""Comment — polymorphic child (post or user), and it broadcasts itself."""

from __future__ import annotations

from almasix.broadcasting import BroadcastsEvents, PrivateChannel
from almasix.orm import HasFactory, Model, relation


class Comment(BroadcastsEvents, HasFactory, Model):
    timestamps = False
    fillable = ("body", "commentable_id", "commentable_type")

    #: M26 — send during the write rather than through the queue, so the demo
    #: can show the broadcast without a worker running.
    broadcasts_now = True

    def broadcast_on(self, event: str):
        """Writes go to the thread the comment belongs to; deletes stay quiet."""
        if event == "deleted":
            return []
        return [PrivateChannel(f"comments.{self.commentable_type}.{self.commentable_id}")]

    @relation
    def commentable(self):
        from app.models.post import Post
        from app.models.user import User

        return self.morph_to("commentable", {"Post": Post, "User": User})
