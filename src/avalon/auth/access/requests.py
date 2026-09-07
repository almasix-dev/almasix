"""``AuthorizesRequests`` — controller ``authorize`` / ``authorize_for_user``."""

from __future__ import annotations

from typing import Any, ClassVar

from avalon.auth.access.facade import Gate
from avalon.auth.access.gate import CONTROLLER_RESOURCE_ABILITIES
from avalon.auth.access.response import AuthorizationResponse


class AuthorizesRequests:
    """Laravel ``AuthorizesRequests`` for HTTP controllers."""

    authorizes_resource: ClassVar[Any] = None

    def authorize(self, ability: str, arguments: Any = None) -> AuthorizationResponse:
        return Gate.authorize(ability, arguments)

    def authorize_for_user(
        self,
        user: Any,
        ability: str,
        arguments: Any = None,
    ) -> AuthorizationResponse:
        return Gate.for_user(user).authorize(ability, arguments)

    def can(self, ability: str, arguments: Any = None) -> bool:
        return Gate.allows(ability, arguments)

    def cannot(self, ability: str, arguments: Any = None) -> bool:
        return Gate.denies(ability, arguments)

    def authorize_when(
        self,
        condition: bool,
        ability: str,
        arguments: Any = None,
    ) -> AuthorizationResponse:
        if condition:
            return self.authorize(ability, arguments)
        return AuthorizationResponse.allow()

    def authorize_unless(
        self,
        condition: bool,
        ability: str,
        arguments: Any = None,
    ) -> AuthorizationResponse:
        return self.authorize_when(not condition, ability, arguments)

    def resource_ability_map(self) -> dict[str, str]:
        return dict(CONTROLLER_RESOURCE_ABILITIES)
