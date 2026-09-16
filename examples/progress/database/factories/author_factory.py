"""AuthorFactory."""

from __future__ import annotations

from typing import Any

from almasix.orm import Factory

from app.models.author import Author


class AuthorFactory(Factory):
    """Builds Author rows for seeders and tests."""

    model = Author

    def definition(self) -> dict[str, Any]:
        """The attributes a fresh Author starts from."""
        return {
            "name": self.fake.name(),
        }
