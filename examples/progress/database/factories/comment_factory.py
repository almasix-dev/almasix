"""CommentFactory."""

from __future__ import annotations

from typing import Any

from app.models.comment import Comment

from almasix.orm import Factory


class CommentFactory(Factory):
    """Builds Comment rows — the polymorphic child of a post or a user."""

    model = Comment

    def definition(self) -> dict[str, Any]:
        """The attributes a fresh Comment starts from."""
        return {"body": self.fake.sentence()}
