"""In-memory token used by ``Signet.acting_as`` and SPA session auth."""

from __future__ import annotations

from collections.abc import Sequence


class TransientToken:
    """Abilities carrier without a database row."""

    def __init__(self, abilities: Sequence[str] | None = None) -> None:
        self.abilities = list(abilities) if abilities is not None else ["*"]

    def can(self, ability: str) -> bool:
        return "*" in self.abilities or ability in self.abilities

    def cant(self, ability: str) -> bool:
        return not self.can(ability)

    async def delete(self) -> None:
        return None
