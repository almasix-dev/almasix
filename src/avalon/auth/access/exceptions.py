"""Authorization exception (HTTP 403 by default, 404 when deny-as-not-found)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from avalon.http.exceptions import HttpException

if TYPE_CHECKING:
    from avalon.auth.access.response import AuthorizationResponse


class AuthorizationException(HttpException):
    """Raised when a gate or policy denies an ability."""

    status_code = 403

    def __init__(
        self,
        message: str = "This action is unauthorized.",
        *,
        status_code: int | None = None,
        response: AuthorizationResponse | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        code = status_code
        if code is None and response is not None and response.status() is not None:
            code = int(response.status())
        super().__init__(message, status_code=code, headers=headers)
        self.response = response

    @classmethod
    def from_response(cls, response: AuthorizationResponse) -> AuthorizationException:
        message = response.message() or "This action is unauthorized."
        status = response.status()
        return cls(message, status_code=status, response=response)
