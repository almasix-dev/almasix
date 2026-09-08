"""ActivityFactory — a factory over a document model (M25)."""

from __future__ import annotations

from typing import Any

from app.models.activity import Activity

from almasix.orm import Factory


class ActivityFactory(Factory):
    """Builds Activity documents for seeders, demos, and tests."""

    model = Activity

    def definition(self) -> dict[str, Any]:
        """The attributes a fresh Activity starts from."""
        return {
            "action": self.fake.random_element(["viewed", "edited", "shared"]),
            "weight": self.fake.number_between(1, 9),
            "tags": ["demo"],
        }

    def heavy(self) -> Factory:
        """A state: the activities `Activity.query().heavy()` finds."""
        return self.state({"weight": 9})
