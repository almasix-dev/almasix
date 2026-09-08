"""Who may listen to a post's channel."""

from __future__ import annotations

from typing import Any

from app.models.post import Post


class PostChannel:
    """Authorization for `posts.{post}`.

    The `post` parameter is annotated with the model, so Almasix looks the
    row up before calling `join` — the same binding a route gets.
    """

    def join(self, user: Any, post: Post) -> bool:
        return bool(user) and post.user_id == user.get_key()
