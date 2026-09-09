"""UserFactory — how a test or a seeder makes a user."""

from __future__ import annotations

from typing import Any

from app.models.user import User

from almasix.orm import Factory


class UserFactory(Factory):
    """Builds User rows for seeders and tests."""

    model = User

    def definition(self) -> dict[str, Any]:
        """The attributes a fresh User starts from."""
        return {
            "name": self.fake.name(),
            "email": self.fake.unique().safe_email(),
            # The model casts `password` to `hashed`, so this is hashed on write.
            "password": "password",
            "email_verified_at": self.fake.date_time_this_month(),
        }

    def unverified(self) -> Factory:
        """A state: somebody who has not clicked the verification link yet."""
        return self.state({"email_verified_at": None})
