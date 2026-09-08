"""Comment — polymorphic child (post or user)."""

from __future__ import annotations

from almasix.orm import HasFactory, Model, relation


class Comment(HasFactory, Model):
    timestamps = False
    fillable = ("body", "commentable_id", "commentable_type")

    @relation
    def commentable(self):
        from app.models.post import Post
        from app.models.user import User

        return self.morph_to("commentable", {"Post": Post, "User": User})
