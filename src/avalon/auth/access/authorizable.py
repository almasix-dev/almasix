"""``Authorizable`` mixin — ``user.can(...)`` / ``cannot`` / ``can_any``."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


class Authorizable:
    """Laravel ``Authorizable`` trait for user models."""

    def can(self, ability: str, arguments: Any = None) -> bool:
        from avalon.auth.access.facade import Gate

        return Gate.for_user(self).allows(ability, arguments)

    def cannot(self, ability: str, arguments: Any = None) -> bool:
        return not self.can(ability, arguments)

    cant = cannot

    def can_any(self, abilities: Sequence[str], arguments: Any = None) -> bool:
        from avalon.auth.access.facade import Gate

        return Gate.for_user(self).any(abilities, arguments)

    canany = can_any
