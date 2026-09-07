"""Authorization response — allow / deny with optional HTTP status."""

from __future__ import annotations

from typing import Any, Self


class AuthorizationResponse:
    """Result of a gate or policy check (Laravel ``Illuminate\\Auth\\Access\\Response``)."""

    def __init__(
        self,
        allowed: bool,
        message: str | None = None,
        code: Any = None,
        *,
        status: int | None = None,
    ) -> None:
        self._allowed = bool(allowed)
        self._message = message
        self._code = code
        self._status = status

    def allowed(self) -> bool:
        return self._allowed

    def denied(self) -> bool:
        return not self._allowed

    def message(self) -> str | None:
        return self._message

    def code(self) -> Any:
        return self._code

    def status(self) -> int | None:
        return self._status

    def authorize(self) -> Self:
        """Raise :class:`AuthorizationException` when denied."""
        if self.denied():
            from avalon.auth.access.exceptions import AuthorizationException

            raise AuthorizationException.from_response(self)
        return self

    def __bool__(self) -> bool:
        return self._allowed

    @classmethod
    def allow(cls, message: str | None = None, code: Any = None) -> AuthorizationResponse:
        return cls(True, message, code)

    @classmethod
    def deny(
        cls,
        message: str | None = None,
        code: Any = None,
        *,
        status: int | None = None,
    ) -> AuthorizationResponse:
        return cls(
            False,
            message if message is not None else "This action is unauthorized.",
            code,
            status=status,
        )

    @classmethod
    def deny_with_status(
        cls,
        status: int,
        message: str | None = None,
        code: Any = None,
    ) -> AuthorizationResponse:
        return cls.deny(message, code, status=int(status))

    @classmethod
    def deny_as_not_found(
        cls,
        message: str | None = None,
        code: Any = None,
    ) -> AuthorizationResponse:
        return cls.deny_with_status(404, message, code)
