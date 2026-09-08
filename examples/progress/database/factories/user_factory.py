"""UserFactory."""

from __future__ import annotations

from typing import Any

from app.models.user import User

from almasix.hashing import Hash
from almasix.orm import Factory


class UserFactory(Factory):
    """Builds User rows for seeders and tests."""

    model = User

    def definition(self) -> dict[str, Any]:
        """The attributes a fresh User starts from."""
        return {
            "name": self.fake.first_name(),
            "email": self.fake.unique().safe_email(),
            "password": Hash.make("password"),
            "email_verified_at": self.fake.date_time_this_month(),
        }

    def unverified(self) -> Factory:
        """A state: somebody who has not clicked the link yet."""
        return self.state({"email_verified_at": None})

    def with_token(self, token: str) -> Factory:
        return self.state({"api_token": token})
