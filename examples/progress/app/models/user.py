"""User — has many posts, belongs to many roles, morphs comments."""

from __future__ import annotations

from almasix.auth import AuthenticatableMixin
from almasix.notifications import MustVerifyEmail, Notifiable
from almasix.orm import Attribute, HasFactory, Model, relation
from almasix.signet import HasApiTokens


class User(HasFactory, HasApiTokens, AuthenticatableMixin, Notifiable, MustVerifyEmail, Model):
    fillable = ("email", "name", "password", "remember_token", "api_token", "email_verified_at")
    hidden = ("password", "remember_token")
    appends = ("display_name",)  # noqa: RUF012

    display_name = Attribute(
        get=lambda _value, attributes: f"{attributes.get('name')} <{attributes.get('email')}>"
    )

    @relation
    def posts(self):
        from app.models.post import Post

        return self.has_many(Post)

    @relation
    def latest_post(self):
        """M41 — one related model per parent, picked in a subquery."""
        from app.models.post import Post

        return self.has_many(Post).latest_of_many()

    @relation
    def roles(self):
        from app.models.role import Role

        return self.belongs_to_many(Role).with_pivot("level")

    @relation
    def comments(self):
        from app.models.comment import Comment

        return self.morph_many(Comment, "commentable")
