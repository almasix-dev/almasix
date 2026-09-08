"""RoleFactory."""

from __future__ import annotations

from typing import Any

from app.models.role import Role

from almasix.orm import Factory


class RoleFactory(Factory):
    """Builds Role rows for the many-to-many demos."""

    model = Role

    def definition(self) -> dict[str, Any]:
        """The attributes a fresh Role starts from."""
        return {"name": self.fake.unique().word()}
