"""HTTP client — ``Http.get`` / fakes / retry / pool / batch (Laravel-shaped)."""

from __future__ import annotations

from avalon.client.batch import Batch
from avalon.client.events import ConnectionFailed, RequestSending, ResponseReceived
from avalon.client.exceptions import (
    BatchInProgressException,
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
from avalon.client.pool import Pool, PoolRequest
from avalon.client.provider import ClientServiceProvider
from avalon.client.request import RecordedRequest
from avalon.client.response import Response

__all__ = [
    "Batch",
    "BatchInProgressException",
    "ClientServiceProvider",
    "ConnectionException",
    "ConnectionFailed",
    "Factory",
    "Http",
    "HttpClientException",
    "OutOfFakeResponses",
    "PendingRequest",
    "PendingRequestException",
    "Pool",
    "PoolRequest",
    "RecordedRequest",
    "RequestException",
    "RequestSending",
    "Response",
    "ResponseReceived",
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
