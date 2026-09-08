"""Auth contracts (Laravel Authenticatable / UserProvider)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Authenticatable(Protocol):
    """User identity contract consumed by guards."""

    def get_auth_identifier_name(self) -> str:  # pragma: no cover - protocol
        ...

    def get_auth_identifier(self) -> Any:  # pragma: no cover - protocol
        ...

    def get_auth_password(self) -> str | None:  # pragma: no cover - protocol
        ...

    def get_remember_token(self) -> str | None:  # pragma: no cover - protocol
        ...

    def set_remember_token(self, token: str | None) -> None:  # pragma: no cover - protocol
        ...

    def get_remember_token_name(self) -> str:  # pragma: no cover - protocol
        ...


class UserProvider(Protocol):
    """Retrieves users for a guard."""

    async def retrieve_by_id(self, identifier: Any) -> Any | None:  # pragma: no cover - protocol
        ...

    async def retrieve_by_token(  # pragma: no cover - protocol
        self, identifier: Any, token: str
    ) -> Any | None:
        ...

    async def update_remember_token(  # pragma: no cover - protocol
        self, user: Any, token: str | None
    ) -> None:
        ...

    async def retrieve_by_credentials(  # pragma: no cover - protocol
        self, credentials: dict[str, Any]
    ) -> Any | None:
        ...

    async def validate_credentials(  # pragma: no cover - protocol
        self, user: Any, credentials: dict[str, Any]
    ) -> bool:
        ...

    async def rehash_password_if_required(  # pragma: no cover - protocol
        self,
        user: Any,
        credentials: dict[str, Any],
        *,
        force: bool = False,
    ) -> None:
        ...
