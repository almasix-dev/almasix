"""AuthorPolicy."""

from __future__ import annotations

from almasix.auth import Policy
from app.models.author import Author


class AuthorPolicy(Policy):
    """AuthorPolicy."""

    def view_any(self, user) -> bool:
        return True

    def view(self, user, author: Author) -> bool:
        return True

    def create(self, user) -> bool:
        return True

    def update(self, user, author: Author) -> bool:
        return False

    def delete(self, user, author: Author) -> bool:
        return False

    def restore(self, user, author: Author) -> bool:
        return False

    def force_delete(self, user, author: Author) -> bool:
        return False
