"""PostPolicy — authors may update/delete their posts; admins pass ``before``."""

from __future__ import annotations

from typing import Any

from app.models.post import Post

from avalon.auth import Policy


class PostPolicy(Policy):
    """Authorize Post abilities."""

    def before(self, user: Any, ability: str) -> bool | None:
        if user is not None and getattr(user, "admin", False):
            return True
        return None

    def view_any(self, user: Any) -> bool:
        return user is not None

    def view(self, user: Any, post: Post) -> bool:
        return True

    def create(self, user: Any) -> bool:
        return user is not None

    def update(self, user: Any, post: Post) -> bool:
        return _same_author(user, post)

    def delete(self, user: Any, post: Post) -> bool:
        if _same_author(user, post):
            return True
        return self.deny("You do not own this post.")


def _same_author(user: Any, post: Post) -> bool:
    user_id = getattr(user, "id", None)
    if user_id is None and hasattr(user, "get_auth_identifier"):
        user_id = user.get_auth_identifier()
    post_user_id = getattr(post, "user_id", None)
    return user_id is not None and user_id == post_user_id
