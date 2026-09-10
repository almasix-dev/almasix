"""ORM demo — users: with_count, where_has, upsert, pivot roles, no lazy load."""

from __future__ import annotations

from app.models.role import Role
from app.models.user import User
from app.support.demo_db import ensure_demo_database
from almasix.http import Controller, Request
from almasix.http.exceptions import NotFoundHttpException
from almasix.orm import ModelNotFoundError, RelationNotLoadedError


class UserController(Controller):
    async def index(self) -> dict:
        """Users with post counts and pivot roles."""
        await ensure_demo_database()
        users = await User.query().with_count("posts").with_("roles").order_by("id").get()
        return {
            "users": [
                {
                    **user.to_dict(),
                    "posts_count": user._extra.get("posts_count", 0),
                }
                for user in users
            ],
            "count": len(users),
        }

    async def authors(self) -> dict:
        """Users who have at least one published post (`where_has`)."""
        await ensure_demo_database()
        users = await (
            User.query()
            .where_has("posts", lambda query: query.where("published", True))
            .order_by("id")
            .get()
        )
        return {"authors": users.to_dict(), "count": len(users)}

    async def posts(self, user: str) -> dict:
        """Relation query: `await user.posts().published().get()`."""
        await ensure_demo_database()
        model = await _user_or_fail(int(user))
        unloaded_raises = False
        try:
            len(model.posts)
        except RelationNotLoadedError:
            unloaded_raises = True
        posts = await model.posts().published().order_by("id").get()
        return {
            "user": model.to_dict(),
            "posts": posts.to_dict(),
            "unloaded_attribute_raises": unloaded_raises,
        }

    async def upsert(self, request: Request) -> dict:
        """Dialect-native upsert (unique on email)."""
        await ensure_demo_database()
        email = str(request.input("email", "ada@almasix.dev"))
        name = str(request.input("name", "Ada Lovelace"))
        await User.query().upsert(
            {"email": email, "name": name},
            unique_by=["email"],
            update=["name"],
        )
        user = await User.query().where("email", email).first()
        return {"user": user.to_dict() if user else None}

    async def attach_role(self, user: str, role: str) -> dict:
        await ensure_demo_database()
        model = await _user_or_fail(int(user))
        found = await Role.query().where("name", role).first()
        if found is None:
            raise NotFoundHttpException(f"Role {role!r} not found")
        await model.roles().sync([found.id], detaching=False)
        roles = await model.roles().get()
        return {"user_id": model.id, "roles": roles.to_dict()}


async def _user_or_fail(user_id: int) -> User:
    try:
        return await User.find_or_fail(user_id)
    except ModelNotFoundError as exc:
        raise NotFoundHttpException(f"User {user_id} not found") from exc
