"""Module-level HTTP client helpers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from avalon.client.facade import Http, get_factory, set_factory
from avalon.client.factory import Factory
from avalon.client.response import Response


def http() -> Factory:
    return get_factory()


def http_get(url: str, query: Mapping[str, Any] | None = None) -> Response:
    return Http.get(url, query)


def http_post(url: str, data: Any = None) -> Response:
    return Http.post(url, data)


def http_fake(callback: Any = None) -> Factory:
    return Http.fake(callback)


def http_assert_sent(callback: str | Callable) -> None:
    Http.assert_sent(callback)


__all__ = [
    "Http",
    "get_factory",
    "http",
    "http_assert_sent",
    "http_fake",
    "http_get",
    "http_post",
    "set_factory",
]
