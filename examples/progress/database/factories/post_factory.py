"""PostFactory."""

from __future__ import annotations

from typing import Any

from app.models.post import Post

from almasix.orm import Factory


class PostFactory(Factory):
    """Builds Post rows for seeders and tests."""

    model = Post

    def definition(self) -> dict[str, Any]:
        """The attributes a fresh Post starts from."""
        return {
            "title": self.fake.title(),
            "published": True,
            "views": self.fake.number_between(0, 500),
        }

    def draft(self) -> Factory:
        """A state: written, not published, unread."""
        return self.state({"published": False, "views": 0})
