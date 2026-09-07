"""HTTP client events — dispatched through the application event dispatcher."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from avalon.client.exceptions import ConnectionException
    from avalon.client.request import RecordedRequest
    from avalon.client.response import Response


@dataclass
class RequestSending:
    """Fired before a request leaves the client."""

    request: RecordedRequest


@dataclass
class ResponseReceived:
    """Fired once a response (real or faked) is available."""

    request: RecordedRequest
    response: Response


@dataclass
class ConnectionFailed:
    """Fired when no response could be obtained for a request."""

    request: RecordedRequest
    exception: ConnectionException
