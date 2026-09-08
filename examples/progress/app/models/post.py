"""Post — belongs to a user; soft deletes + published scope."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from avalon.orm import Model, Prunable, SoftDeletes, relation


class Post(Prunable, SoftDeletes, Model):
    fillable = ("title", "user_id", "published", "views")
    casts = {"published": "bool", "views": "int"}  # noqa: RUF012

    def scope_published(query):
        return query.where("published", True)

    def prunable(self):
        """`grail model:prune` deletes posts trashed more than a week ago."""
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
        return self.only_trashed().where("deleted_at", "<", cutoff)

    @relation
    def author(self):
        from app.models.user import User

        return self.belongs_to(User)

    @relation
    def comments(self):
        from app.models.comment import Comment

        return self.morph_many(Comment, "commentable")
