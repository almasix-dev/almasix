"""Turning a resolved resource into an HTTP response — wrapping and meta."""

from __future__ import annotations

import datetime as _datetime
import decimal
import json
import uuid
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from fastapi.responses import JSONResponse

from almasix.http.resources.collection import is_paginator


class ResourceJSONResponse(JSONResponse):
    """A JSON response that knows how to render dates, decimals, and UUIDs."""

    def render(self, content: Any) -> bytes:
        return json.dumps(content, ensure_ascii=False, default=_encode).encode("utf-8")


def _encode(value: Any) -> Any:
    if isinstance(value, (_datetime.datetime, _datetime.date, _datetime.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    serializer = getattr(value, "to_dict", None)
    if callable(serializer):
        return serializer()
    return str(value)


class ResourceResponse:
    """Builds the response for a resource, wrapping data the Laravel way."""

    def __init__(self, resource: Any) -> None:
        self.resource = resource

    def to_response(self, request: Any = None) -> JSONResponse:
        if request is None:
            request = _current_request()

        data = self.resource.resolve(request)
        paginated = _paginator_for(self.resource)
        extra = self._extra(request, paginated)
        payload = self._wrap(data, extra, forced=paginated is not None)

        response = ResourceJSONResponse(
            payload,
            status_code=self.resource._status,
            headers=self.resource._headers or None,
        )
        self.resource.with_response(request, response)
        return response

    # --- internals -------------------------------------------------------

    def _extra(self, request: Any, paginated: Any) -> dict[str, Any]:
        extra: dict[str, Any] = {}
        if paginated is not None:
            default = pagination_information(request, paginated)
            hook = getattr(self.resource, "pagination_information", None)
            extra.update(hook(request, paginated, default) if hook else default)
        extra.update(self.resource.with_(request))
        extra.update(self.resource._additional)
        return extra

    def _wrap(self, data: Any, extra: dict[str, Any], forced: bool) -> Any:
        key = self.resource.wrapping_key()
        if key is None and forced:
            # A paginated payload has nowhere to put `meta` unless its rows
            # live under a key, so pagination wins over `without_wrapping`.
            key = "data"
        if key is None:
            if isinstance(data, Mapping):
                return {**data, **extra}
            return {"data": data, **extra} if extra else data
        if isinstance(data, Mapping) and key in data:
            # Already shaped like `{"data": ...}`; don't wrap it twice.
            return {**data, **extra}
        return {key: data, **extra}


def pagination_information(request: Any, paginated: Any) -> dict[str, Any]:
    """Laravel's ``meta`` / ``links`` block for a paginated collection."""
    path = _path_for(request)
    meta: dict[str, Any] = {
        "current_page": paginated.current_page,
        "per_page": paginated.per_page,
    }
    if hasattr(paginated, "total"):
        meta.update(
            {
                "from": paginated.from_,
                "last_page": paginated.last_page,
                "to": paginated.to,
                "total": paginated.total,
            }
        )
    else:
        meta["has_more"] = paginated.has_more_pages()
    if path is not None:
        meta["path"] = path
    information: dict[str, Any] = {"meta": meta}
    links = _links_for(path, paginated)
    if links is not None:
        information["links"] = links
    return information


def _links_for(path: str | None, paginated: Any) -> dict[str, str | None] | None:
    """First / last / prev / next, but only when the URL is actually known."""
    if path is None:
        return None
    last_page = getattr(paginated, "last_page", None)
    links: dict[str, str | None] = {
        "first": _page_url(path, 1),
        "last": _page_url(path, last_page) if last_page is not None else None,
        "prev": _page_url(path, paginated.current_page - 1)
        if not paginated.on_first_page()
        else None,
        "next": _page_url(path, paginated.current_page + 1) if paginated.has_more_pages() else None,
    }
    return links


def _page_url(path: str, page: int) -> str:
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}{urlencode({'page': page})}"


def _path_for(request: Any) -> str | None:
    """The request URL without its query string, or ``None`` off-request."""
    url = getattr(request, "url", None)
    if not url:
        return None
    parts = urlsplit(str(url))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _paginator_for(resource: Any) -> Any | None:
    underlying = getattr(resource, "resource", None)
    return underlying if is_paginator(underlying) else None


def _current_request() -> Any:
    from almasix.http.request import get_request

    return get_request()
