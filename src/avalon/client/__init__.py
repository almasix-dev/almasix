"""HTTP client — ``Http.get`` / fakes / retry / pool (Laravel-shaped)."""

from __future__ import annotations

from avalon.client.exceptions import (
    ConnectionException,
    HttpClientException,
    OutOfFakeResponses,
    PendingRequestException,
    RequestException,
    StrayRequestException,
)
from avalon.client.facade import Http, get_factory, set_factory
from avalon.client.factory import Factory, Sequence
from avalon.client.helpers import http, http_assert_sent, http_fake, http_get, http_post
from avalon.client.pending import PendingRequest
from avalon.client.pool import Pool
from avalon.client.provider import ClientServiceProvider
from avalon.client.request import RecordedRequest
from avalon.client.response import Response

__all__ = [
    "ClientServiceProvider",
    "ConnectionException",
    "Factory",
    "Http",
    "HttpClientException",
    "OutOfFakeResponses",
    "PendingRequest",
    "PendingRequestException",
    "Pool",
    "RecordedRequest",
    "RequestException",
    "Response",
    "Sequence",
    "StrayRequestException",
    "get_factory",
    "http",
    "http_assert_sent",
    "http_fake",
    "http_get",
    "http_post",
    "set_factory",
]
