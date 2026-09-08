"""HTTP client — ``Http.get`` / fakes / retry / pool / batch (Laravel-shaped)."""

from __future__ import annotations

from almasix.client.batch import Batch
from almasix.client.events import ConnectionFailed, RequestSending, ResponseReceived
from almasix.client.exceptions import (
    BatchInProgressException,
    ConnectionException,
    HttpClientException,
    OutOfFakeResponses,
    PendingRequestException,
    RequestException,
    StrayRequestException,
)
from almasix.client.facade import Http, get_factory, set_factory
from almasix.client.factory import Factory, Sequence
from almasix.client.helpers import http, http_assert_sent, http_fake, http_get, http_post
from almasix.client.pending import PendingRequest
from almasix.client.pool import Pool, PoolRequest
from almasix.client.provider import ClientServiceProvider
from almasix.client.request import RecordedRequest
from almasix.client.response import Response

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
