"""HTTP exceptions with a consistent JSON error shape."""

from __future__ import annotations

from typing import Any


class HttpException(Exception):
    """Base HTTP exception rendered as JSON by the HTTP kernel."""

    status_code: int = 500

    def __init__(
        self,
        message: str = "Server Error",
        *,
        status_code: int | None = None,
        errors: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.errors = errors or {}
        self.headers = headers or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "status": self.status_code,
            "errors": dict(self.errors),
        }


class BadRequestHttpException(HttpException):
    status_code = 400


class UnauthorizedHttpException(HttpException):
    status_code = 401


class ForbiddenHttpException(HttpException):
    status_code = 403


class NotFoundHttpException(HttpException):
    status_code = 404


class MethodNotAllowedHttpException(HttpException):
    status_code = 405


class UnprocessableEntityHttpException(HttpException):
    status_code = 422


class TooManyRequestsHttpException(HttpException):
    status_code = 429


class ServiceUnavailableHttpException(HttpException):
    status_code = 503
