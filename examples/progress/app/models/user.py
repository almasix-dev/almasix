"""User — has many posts, belongs to many roles, morphs comments."""

from __future__ import annotations

from avalon.auth import AuthenticatableMixin
from avalon.notifications import MustVerifyEmail, Notifiable
from avalon.orm import Attribute, Model, relation


class User(AuthenticatableMixin, Notifiable, MustVerifyEmail, Model):
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
    def roles(self):
        from app.models.role import Role

        return self.belongs_to_many(Role).with_pivot("level")

    @relation
    def comments(self):
        from app.models.comment import Comment

        return self.morph_many(Comment, "commentable")
