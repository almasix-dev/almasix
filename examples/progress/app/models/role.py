"""Role — many-to-many with users."""

from __future__ import annotations

from almasix.orm import Model, relation


class Role(Model):
    timestamps = False
    fillable = ("name",)

    @relation
    def users(self):
        from app.models.user import User

        return self.belongs_to_many(User)
