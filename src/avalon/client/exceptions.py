"""HTTP client exceptions (Laravel-shaped)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from avalon.client.response import Response


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
    """Non-successful HTTP response (typically 4xx / 5xx)."""

    def __init__(self, response: Response) -> None:
        self.response = response
        super().__init__(
            f"HTTP request returned status code {response.status()}.",
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self.response, name)


class PendingRequestException(HttpClientException):
    """The pending request could not be sent as configured."""
