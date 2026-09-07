"""HTTP client exceptions (Laravel-shaped)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from avalon.client.response import Response


def _message_for(response: Response, truncate_at: int | None) -> str:
    message = f"HTTP request returned status code {response.status()}"
    body = response.body().strip()
    if not body:
        return f"{message}."
    if truncate_at is not None and len(body) > truncate_at:
        body = f"{body[:truncate_at]}..."
    return f"{message}:\n{body}\n"


class HttpClientException(Exception):
    """Base HTTP client error."""


class ConnectionException(HttpClientException):
    """Transport / connection failure (DNS, timeout, refused)."""


class StrayRequestException(HttpClientException):
    """A request was sent that has no matching fake."""

    def __init__(self, method: str, url: str) -> None:
        self.method = method
        self.url = url
        super().__init__(f"Attempted request to {method} {url} without a matching fake.")


class OutOfFakeResponses(HttpClientException):
    """A fake sequence ran out of queued responses."""


class RequestException(HttpClientException):
    """Non-successful HTTP response (typically 4xx / 5xx).

    The message carries the response body, truncated to 120 characters like
    Laravel. Change that globally with :meth:`truncate_at` /
    :meth:`dont_truncate`, or per request with
    ``Http.truncate_exceptions_at(...)``.
    """

    _truncate_at: int | None = 120

    def __init__(self, response: Response, truncate_at: int | None = None) -> None:
        self.response = response
        limit = truncate_at if truncate_at is not None else type(self)._truncate_at
        super().__init__(_message_for(response, limit))

    @classmethod
    def truncate_at(cls, length: int) -> None:
        cls._truncate_at = length

    @classmethod
    def dont_truncate(cls) -> None:
        cls._truncate_at = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.response, name)


class PendingRequestException(HttpClientException):
    """The pending request could not be sent as configured."""


class BatchInProgressException(HttpClientException):
    """A batch that has already been sent cannot be changed."""
