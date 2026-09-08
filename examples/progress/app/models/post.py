"""Post — belongs to a user; soft deletes + published scope."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from almasix.orm import HasFactory, Model, Prunable, SoftDeletes, relation
from almasix.scout import Searchable


class Post(Searchable, HasFactory, Prunable, SoftDeletes, Model):
    fillable = ("title", "user_id", "published", "views")
    casts = {"published": "bool", "views": "int"}  # noqa: RUF012

    # M27 — what `Post.search()` looks in, and what reaches the index.
    searchable_columns = ("title",)

    def to_searchable_array(self):
        return {"id": self.id, "title": self.title, "user_id": self.user_id}

    def should_be_searchable(self):
        """Drafts stay out of the index until they are published."""
        return bool(self.published)

    def scope_published(query):
        return query.where("published", True)

    def prunable(self):
        """`smith model:prune` deletes posts trashed more than a week ago."""
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=7)
        return self.only_trashed().where("deleted_at", "<", cutoff)

    @relation
    def author(self):
        from app.models.user import User

        return self.belongs_to(User)

    @relation
    def author_or_ghost(self):
        """M41 — a placeholder model instead of `None` when nobody owns the post."""
        from app.models.user import User

        return self.belongs_to(User).with_default({"name": "Ghost Writer"})

    @relation
    def comments(self):
        from app.models.comment import Comment

        # M41 chaperone — each comment gets this post as its `commentable`,
        # so walking children and reading the parent costs no extra query.
        return self.morph_many(Comment, "commentable").chaperone("commentable")
