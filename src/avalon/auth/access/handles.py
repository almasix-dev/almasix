"""``HandlesAuthorization`` helpers for policy classes."""

from __future__ import annotations

from typing import Any

from avalon.auth.access.response import AuthorizationResponse


class HandlesAuthorization:
    """Laravel ``HandlesAuthorization`` — ``allow`` / ``deny`` from policies."""

    def allow(self, message: str | None = None, code: Any = None) -> AuthorizationResponse:
        return AuthorizationResponse.allow(message, code)

    def deny(
        self,
        message: str | None = None,
        code: Any = None,
        *,
        status: int | None = None,
    ) -> AuthorizationResponse:
        return AuthorizationResponse.deny(message, code, status=status)

    def deny_with_status(
        self,
        status: int,
        message: str | None = None,
        code: Any = None,
    ) -> AuthorizationResponse:
        return AuthorizationResponse.deny_with_status(status, message, code)

    def deny_as_not_found(
        self,
        message: str | None = None,
        code: Any = None,
    ) -> AuthorizationResponse:
        return AuthorizationResponse.deny_as_not_found(message, code)
