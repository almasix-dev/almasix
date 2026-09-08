"""Activity — M25: an Articulate model whose rows are documents.

Nothing about the surface changes: casts, scopes, soft deletes, factories, and
relations all work. Only the storage does — `activities` is a collection in a
document store, and there is no migration for it.
"""

from __future__ import annotations

from almasix.config import env
from almasix.orm import Document, EmbeddedDocument, HasFactory, SoftDeletes, relation


class Location(EmbeddedDocument):
    """Where an activity happened — embedded, so it needs no collection."""

    fields = ("city", "country")


class Activity(HasFactory, SoftDeletes, Document):
    connection = env("DOCUMENTS_CONNECTION", "documents")
    collection = "activities"

    fillable = ("action", "user_id", "weight", "tags", "location")
    casts = {"weight": "int"}  # noqa: RUF012

    #: `smith documents:index` creates these; a store needs no migration.
    indexes = (  # noqa: RUF012
        {"keys": [("action", 1)], "name": "action_asc"},
        {"keys": [("user_id", 1), ("weight", -1)], "name": "user_weight"},
    )

    def scope_heavy(query, floor: int = 5):
        return query.where("weight", ">=", floor)

    @relation
    def user(self):
        """A reference across stores: the key is here, the user is in SQL."""
        from app.models.user import User

        return self.belongs_to(User, "user_id", "id")

    @relation
    def location(self):
        return self.embeds_one(Location)
