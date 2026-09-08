"""Role — many-to-many with users."""

from __future__ import annotations

from almasix.orm import HasFactory, Model, relation


class Role(HasFactory, Model):
    timestamps = False
    fillable = ("name",)

    @relation
    def users(self):
        from app.models.user import User

        return self.belongs_to_many(User)
