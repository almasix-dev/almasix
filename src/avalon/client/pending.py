"""Fluent pending HTTP request (Laravel ``PendingRequest``)."""

from __future__ import annotations

import asyncio
import copy
import json
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx

from avalon.client.arity import accepts_two_arguments
from avalon.client.events import ConnectionFailed, RequestSending, ResponseReceived
from avalon.client.exceptions import (
    ConnectionException,
    PendingRequestException,
    RequestException,
    StrayRequestException,
)
from avalon.client.request import RecordedRequest
from avalon.client.response import Response
from avalon.client.uri_template import expand as expand_uri_template
from avalon.events import Event

_JSON_TYPES = (dict, list)
_BODY_FORMATS = frozenset({"json", "form", "multipart", "body"})



class PendingRequest:
    """Builder that sends one HTTP request (or a lazy pool job)."""

    def __init__(self, factory: Any) -> None:
        self._factory = factory
        self.headers: dict[str, str] = {}
        self._query: dict[str, Any] = {}
        self._url_params: dict[str, Any] = {}
        self._cookies: dict[str, str] = {}
        self._timeout: float | None = 30.0
        self._connect_timeout: float | None = 10.0
        self._tries: int = 1
        self._retry_sleep: Any = 0
        self._retry_when: Callable[..., bool] | None = None
        self._retry_throw: bool = True
        self._mutable: bool = False
        self._throw: bool = False
        self._throw_if: Callable[[Response], bool] | bool | None = None
        self._throw_callback: Callable[[Response], Any] | None = None
        self._base_url: str = ""
        self._options: dict[str, Any] = {}
        self._middleware: list[Callable[[RecordedRequest], RecordedRequest]] = []
        self._response_middleware: list[Callable[[Response], Response]] = []
        self._before_sending: list[Callable[[RecordedRequest], Any]] = []
        self._body_format: str | None = None
        self._accept: str | None = None
        self._auth: Any = None
        self._files: dict[str, Any] = {}
        self._sink: Any = None
        self._truncate_at: int | None = None

    def _clone(self) -> PendingRequest:
        if self._mutable:
            # Inside a ``retry`` callback the request is live, as in Laravel, so
            # fluent calls reconfigure the next attempt instead of forking.
            return self
        cloned = copy.copy(self)
        cloned.headers = dict(self.headers)
        cloned._query = dict(self._query)
        cloned._url_params = dict(self._url_params)
        cloned._cookies = dict(self._cookies)
        cloned._options = dict(self._options)
        cloned._middleware = list(self._middleware)
        cloned._response_middleware = list(self._response_middleware)
        cloned._before_sending = list(self._before_sending)
        cloned._files = dict(self._files)
        return cloned

    def with_headers(self, headers: Mapping[str, Any]) -> PendingRequest:
        cloned = self._clone()
        cloned.headers.update({str(k): str(v) for k, v in headers.items()})
        return cloned

    def with_header(self, name: str, value: Any) -> PendingRequest:
        return self.with_headers({name: value})

    def replace_headers(self, headers: Mapping[str, Any]) -> PendingRequest:
        cloned = self._clone()
        cloned.headers = {str(k): str(v) for k, v in headers.items()}
        return cloned

    def with_token(self, token: str, type: str = "Bearer") -> PendingRequest:
        return self.with_header("Authorization", f"{type} {token}".strip())

    def with_user_agent(self, user_agent: str) -> PendingRequest:
        return self.with_header("User-Agent", user_agent)

    def with_basic_auth(self, username: str, password: str) -> PendingRequest:
        cloned = self._clone()
        cloned._auth = (username, password)
        return cloned

    def with_digest_auth(self, username: str, password: str) -> PendingRequest:
        cloned = self._clone()
        cloned._auth = httpx.DigestAuth(username, password)
        return cloned

    def with_url_parameters(self, parameters: Mapping[str, Any]) -> PendingRequest:
        cloned = self._clone()
        cloned._url_params.update(parameters)
        return cloned

    def with_query_parameters(self, parameters: Mapping[str, Any]) -> PendingRequest:
        cloned = self._clone()
        cloned._query.update(dict(parameters))
        return cloned

    def with_cookies(self, cookies: Mapping[str, str]) -> PendingRequest:
        cloned = self._clone()
        cloned._cookies.update(dict(cookies))
        return cloned

    def with_cookie(self, name: str, value: str) -> PendingRequest:
        return self.with_cookies({name: value})

    def timeout(self, seconds: float) -> PendingRequest:
        cloned = self._clone()
        cloned._timeout = float(seconds)
        return cloned

    def connect_timeout(self, seconds: float) -> PendingRequest:
        cloned = self._clone()
        cloned._connect_timeout = float(seconds)
        return cloned

    def retry(
        self,
        times: int | list[float],
        sleep: float | list[float] | Callable[..., float] = 0,
        when: Callable[..., bool] | None = None,
        throw: bool = True,
    ) -> PendingRequest:
        """Attempt a request up to ``times`` times, sleeping ``sleep`` ms between.

        ``times`` may be a list of millisecond delays instead, in which case the
        attempt count is derived from it. ``sleep`` may also be a list of delays
        or a callable receiving ``(attempt[, error])``.
        """
        cloned = self._clone()
        if isinstance(times, (list, tuple)):
            cloned._retry_sleep = list(times)
            cloned._tries = len(times) + 1
        else:
            cloned._tries = max(1, int(times))
            cloned._retry_sleep = list(sleep) if isinstance(sleep, (list, tuple)) else sleep
        cloned._retry_when = when
        cloned._retry_throw = throw
        return cloned

    def with_options(self, options: Mapping[str, Any]) -> PendingRequest:
        cloned = self._clone()
        cloned._options.update(dict(options))
        return cloned

    def with_middleware(self, middleware: Callable[[RecordedRequest], RecordedRequest]) -> PendingRequest:
        cloned = self._clone()
        cloned._middleware.append(middleware)
        return cloned

    def with_request_middleware(
        self, middleware: Callable[[RecordedRequest], RecordedRequest]
    ) -> PendingRequest:
        return self.with_middleware(middleware)

    def with_response_middleware(self, middleware: Callable[[Response], Response]) -> PendingRequest:
        cloned = self._clone()
        cloned._response_middleware.append(middleware)
        return cloned

    def before_sending(self, callback: Callable[[RecordedRequest], Any]) -> PendingRequest:
        cloned = self._clone()
        cloned._before_sending.append(callback)
        return cloned

    def as_json(self) -> PendingRequest:
        cloned = self._clone()
        cloned._body_format = "json"
        cloned.headers.setdefault("Content-Type", "application/json")
        cloned.headers.setdefault("Accept", "application/json")
        return cloned

    def as_form(self) -> PendingRequest:
        cloned = self._clone()
        cloned._body_format = "form"
        cloned.headers["Content-Type"] = "application/x-www-form-urlencoded"
        return cloned

    def as_multipart(self) -> PendingRequest:
        cloned = self._clone()
        cloned._body_format = "multipart"
        cloned.headers.pop("Content-Type", None)
        return cloned

    def body_format(self, format: str) -> PendingRequest:
        if format not in _BODY_FORMATS:
            raise PendingRequestException(
                f"Unknown body format {format!r}; expected one of {sorted(_BODY_FORMATS)}."
            )
        cloned = self._clone()
        cloned._body_format = format
        return cloned

    def content_type(self, content_type: str) -> PendingRequest:
        return self.with_header("Content-Type", content_type)

    def accept(self, content_type: str) -> PendingRequest:
        cloned = self._clone()
        cloned._accept = content_type
        cloned.headers["Accept"] = content_type
        return cloned

    def accept_json(self) -> PendingRequest:
        return self.accept("application/json")

    def with_body(self, content: Any, content_type: str | None = None) -> PendingRequest:
        cloned = self._clone()
        cloned._options["content"] = content
        cloned._body_format = "body"
        if content_type is not None:
            cloned.headers["Content-Type"] = content_type
        return cloned

    def truncate_exceptions_at(self, length: int) -> PendingRequest:
        cloned = self._clone()
        cloned._truncate_at = length
        return cloned

    def attach(
        self,
        name: str,
        contents: Any,
        filename: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> PendingRequest:
        cloned = self.as_multipart()
        entry: Any
        if headers:
            entry = (filename or name, contents, None, dict(headers))
        else:
            entry = (filename or name, contents)
        cloned._files[name] = entry
        return cloned

    def sink(self, dest: Any) -> PendingRequest:
        cloned = self._clone()
        cloned._sink = dest
        return cloned

    def base_url(self, url: str) -> PendingRequest:
        cloned = self._clone()
        cloned._base_url = url.rstrip("/")
        return cloned

    def throw(self, callback: Callable[[Response], Any] | None = None) -> PendingRequest:
        cloned = self._clone()
        cloned._throw = True
        cloned._throw_callback = callback
        return cloned

    def throw_if(self, condition: bool | Callable[[Response], bool]) -> PendingRequest:
        cloned = self._clone()
        cloned._throw = True
        cloned._throw_if = condition
        return cloned

    def throw_unless(self, condition: bool | Callable[[Response], bool]) -> PendingRequest:
        cloned = self._clone()
        cloned._throw = True
        cloned._throw_if = (
            (lambda resp: not condition(resp))
            if callable(condition)
            else (not bool(condition))
        )
        return cloned

    def when(
        self,
        condition: Any,
        callback: Callable[[PendingRequest], PendingRequest],
        default: Callable[[PendingRequest], PendingRequest] | None = None,
    ) -> PendingRequest:
        if callable(condition):
            condition = condition(self)
        if condition:
            return callback(self)
        if default is not None:
            return default(self)
        return self

    def unless(
        self,
        condition: Any,
        callback: Callable[[PendingRequest], PendingRequest],
        default: Callable[[PendingRequest], PendingRequest] | None = None,
    ) -> PendingRequest:
        if callable(condition):
            condition = condition(self)
        return self.when(not condition, callback, default)

    def dump(self, *values: Any) -> PendingRequest:
        from avalon.debug import dump

        dump(*(values or (self._debug_payload(),)))
        return self

    def dd(self, *values: Any) -> None:
        from avalon.debug import dd

        dd(*(values or (self._debug_payload(),)))

    def _debug_payload(self) -> dict[str, Any]:
        return {
            "headers": dict(self.headers),
            "query": dict(self._query),
            "base_url": self._base_url,
            "timeout": self._timeout,
            "tries": self._tries,
        }

    def get(self, url: str, query: Mapping[str, Any] | None = None) -> Response:
        pending = self.with_query_parameters(query) if query else self
        return pending.send("GET", url)

    def head(self, url: str, query: Mapping[str, Any] | None = None) -> Response:
        pending = self.with_query_parameters(query) if query else self
        return pending.send("HEAD", url)

    def post(self, url: str, data: Any = None) -> Response:
        return self.send("POST", url, data)

    def put(self, url: str, data: Any = None) -> Response:
        return self.send("PUT", url, data)

    def patch(self, url: str, data: Any = None) -> Response:
        return self.send("PATCH", url, data)

    def delete(self, url: str, data: Any = None) -> Response:
        return self.send("DELETE", url, data)

    def options(self, url: str, data: Any = None) -> Response:
        return self.send("OPTIONS", url, data)

    async def aget(self, url: str, query: Mapping[str, Any] | None = None) -> Response:
        pending = self.with_query_parameters(query) if query else self
        return await pending.send_async("GET", url)

    async def ahead(self, url: str, query: Mapping[str, Any] | None = None) -> Response:
        pending = self.with_query_parameters(query) if query else self
        return await pending.send_async("HEAD", url)

    async def apost(self, url: str, data: Any = None) -> Response:
        return await self.send_async("POST", url, data)

    async def aput(self, url: str, data: Any = None) -> Response:
        return await self.send_async("PUT", url, data)

    async def apatch(self, url: str, data: Any = None) -> Response:
        return await self.send_async("PATCH", url, data)

    async def adelete(self, url: str, data: Any = None) -> Response:
        return await self.send_async("DELETE", url, data)

    async def aoptions(self, url: str, data: Any = None) -> Response:
        return await self.send_async("OPTIONS", url, data)

    def send(self, method: str, url: str, data: Any = None) -> Response:
        request = self._retry_view()
        attempt = 0
        while True:
            attempt += 1
            try:
                response = request._dispatch(method, url, data)
            except ConnectionException as exc:
                if attempt >= request._tries or not request._should_retry(exc):
                    raise
                request._wait(attempt, exc)
                continue
            error = request._retry_error(response)
            if error is None:
                return request._finalize(response)
            if attempt >= request._tries:
                return request._finalize(response, exhausted=True)
            request._wait(attempt, error)

    async def send_async(self, method: str, url: str, data: Any = None) -> Response:
        request = self._retry_view()
        attempt = 0
        while True:
            attempt += 1
            try:
                response = await request._dispatch_async(method, url, data)
            except ConnectionException as exc:
                if attempt >= request._tries or not request._should_retry(exc):
                    raise
                await request._wait_async(attempt, exc)
                continue
            error = request._retry_error(response)
            if error is None:
                return request._finalize(response)
            if attempt >= request._tries:
                return request._finalize(response, exhausted=True)
            await request._wait_async(attempt, error)

    def _retry_view(self) -> PendingRequest:
        """A live request for the retry loop, so ``when`` can reconfigure attempts."""
        if self._tries <= 1:
            return self
        view = self._clone()
        view._mutable = True
        return view

    def _retry_error(self, response: Response) -> RequestException | None:
        """The error worth retrying, or ``None`` when this response is final."""
        if self._tries == 1 or not response.failed():
            return None
        error = RequestException(response)
        return error if self._should_retry(error) else None

    def _should_retry(self, error: BaseException) -> bool:
        """Laravel default: retry every failure; ``when`` narrows it."""
        if self._retry_when is None:
            return True
        if accepts_two_arguments(self._retry_when):
            return bool(self._retry_when(error, self))
        return bool(self._retry_when(error))

    def _sleep_for(self, attempt: int, subject: Any) -> float:
        """Seconds to wait before the next attempt (``sleep`` is milliseconds)."""
        sleep = self._retry_sleep
        if callable(sleep):
            sleep = sleep(attempt, subject) if accepts_two_arguments(sleep) else sleep(attempt)
        elif isinstance(sleep, list):
            sleep = sleep[min(attempt, len(sleep)) - 1] if sleep else 0
        return max(0.0, float(sleep)) / 1000.0

    def _wait(self, attempt: int, subject: Any) -> None:
        delay = self._sleep_for(attempt, subject)
        if delay > 0:
            time.sleep(delay)

    async def _wait_async(self, attempt: int, subject: Any) -> None:
        delay = self._sleep_for(attempt, subject)
        if delay > 0:
            await asyncio.sleep(delay)

    def _finalize(self, response: Response, *, exhausted: bool = False) -> Response:
        for mw in self._factory.response_middleware() + self._response_middleware:
            response = mw(response) or response
        if (exhausted and self._retry_throw) or (
            self._throw and self._throw_condition_met(response)
        ):
            # ``Response.throw`` is a no-op for successful responses.
            response.throw(self._throw_callback, truncate_at=self._truncate_at)
        return response

    def _throw_condition_met(self, response: Response) -> bool:
        if self._throw_if is None:
            return True
        if callable(self._throw_if):
            return bool(self._throw_if(response))
        return bool(self._throw_if)

    def _dispatch(self, method: str, url: str, data: Any) -> Response:
        recorded = self._build_recorded(method, url, data)
        stub = self._factory.match_stub(recorded)
        Event.dispatch(RequestSending(recorded))
        if stub is not None:
            return self._record(recorded, self._coerce_stub(stub, recorded))
        self._guard_stray(recorded)
        try:
            response = self._send_httpx(recorded)
        except ConnectionException as exc:
            Event.dispatch(ConnectionFailed(recorded, exc))
            raise
        return self._record(recorded, response)

    async def _dispatch_async(self, method: str, url: str, data: Any) -> Response:
        recorded = self._build_recorded(method, url, data)
        stub = self._factory.match_stub(recorded)
        Event.dispatch(RequestSending(recorded))
        if stub is not None:
            return self._record(recorded, self._coerce_stub(stub, recorded))
        self._guard_stray(recorded)
        try:
            response = await self._send_httpx_async(recorded)
        except ConnectionException as exc:
            Event.dispatch(ConnectionFailed(recorded, exc))
            raise
        return self._record(recorded, response)

    def _guard_stray(self, recorded: RecordedRequest) -> None:
        """Laravel executes un-faked URLs for real unless strays are prevented."""
        if self._factory.stray_allowed(recorded):
            return
        raise StrayRequestException(recorded.method, recorded.url)

    def _record(self, recorded: RecordedRequest, response: Response) -> Response:
        self._factory.record(recorded, response)
        Event.dispatch(ResponseReceived(recorded, response))
        return response

    def _coerce_stub(self, stub: Any, recorded: RecordedRequest) -> Response:
        if callable(stub) and not isinstance(stub, Response):
            stub = stub(recorded)
        if isinstance(stub, RequestException):
            stub.response._request = recorded
            raise stub
        if isinstance(stub, Exception):
            raise stub
        if isinstance(stub, Response):
            # Stubs are reused across requests, so each dispatch tags its own copy.
            return stub.with_request(recorded)
        if isinstance(stub, int):
            return Response.make(None, stub)
        return Response.make(stub, 200)

    def _build_recorded(self, method: str, url: str, data: Any) -> RecordedRequest:
        full = self._expand_url(url)
        body: bytes | str | None = None
        payload = data
        headers = dict(self.headers)
        for extra in self._factory.global_headers():
            headers.setdefault(extra, self._factory.global_headers()[extra])
        if self._accept:
            headers.setdefault("Accept", self._accept)
        fmt = self._body_format
        if payload is not None and fmt is None and isinstance(payload, _JSON_TYPES):
            fmt = "json"
        if fmt == "json" and payload is not None:
            body = json.dumps(payload)
            headers.setdefault("Content-Type", "application/json")
        elif fmt == "form" and payload is not None:
            body = urlencode(payload, doseq=True) if isinstance(payload, Mapping) else str(payload)
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        elif payload is not None and not isinstance(payload, _JSON_TYPES):
            body = payload if isinstance(payload, (bytes, str)) else str(payload)
        content_opt = self._options.get("content")
        if content_opt is not None:
            body = content_opt
            payload = content_opt
        recorded = RecordedRequest(
            method=method.upper(),
            url=full,
            headers=headers,
            data=payload,
            body=body,
            files=dict(self._files) or None,
            cookies=dict(self._cookies),
        )
        for mw in self._factory.request_middleware() + self._middleware:
            recorded = mw(recorded) or recorded
        for hook in self._before_sending:
            hook(recorded)
        return recorded

    def _expand_url(self, url: str) -> str:
        if self._url_params:
            url = expand_uri_template(url, self._url_params)
        if self._base_url and not url.lower().startswith(("http://", "https://")):
            url = urljoin(self._base_url + "/", url.lstrip("/"))
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query.update({str(k): v for k, v in self._query.items()})
        encoded = urlencode(query, doseq=True)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, encoded, parts.fragment))

    def _httpx_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(self._timeout, connect=self._connect_timeout)

    def _httpx_kwargs(self, recorded: RecordedRequest) -> tuple[dict[str, Any], dict[str, Any]]:
        """Split options into ``httpx.Client(...)`` and ``client.request(...)`` kwargs."""
        kwargs: dict[str, Any] = dict(self._options)
        kwargs.pop("content", None)
        client_kwargs: dict[str, Any] = {"timeout": self._httpx_timeout()}
        transport = kwargs.pop("transport", None)
        if transport is not None:
            client_kwargs["transport"] = transport
        if recorded.cookies:
            client_kwargs["cookies"] = recorded.cookies
        kwargs["headers"] = recorded.headers
        if self._auth is not None:
            kwargs["auth"] = self._auth
        if recorded.files:
            kwargs["files"] = recorded.files
            if isinstance(recorded.data, Mapping):
                kwargs["data"] = recorded.data
        elif self._body_format == "json" or (
            recorded.data is not None and isinstance(recorded.data, _JSON_TYPES) and self._body_format is None
        ):
            kwargs["json"] = recorded.data
        elif recorded.body is not None and self._body_format != "form":
            kwargs["content"] = recorded.body
        elif self._body_format == "form" and isinstance(recorded.data, Mapping):
            kwargs["data"] = recorded.data
        elif recorded.body is not None:
            kwargs["content"] = recorded.body
        kwargs["follow_redirects"] = kwargs.get("follow_redirects", True)
        return client_kwargs, kwargs

    def _write_sink(self, response: Response) -> None:
        if self._sink is None:
            return
        data = response.content()
        dest = self._sink
        if hasattr(dest, "write"):
            dest.write(data)
            return
        path = dest
        with open(path, "wb") as handle:
            handle.write(data)

    def _send_httpx(self, recorded: RecordedRequest) -> Response:
        client_kwargs, kwargs = self._httpx_kwargs(recorded)
        try:
            with httpx.Client(**client_kwargs) as client:
                raw = client.request(recorded.method, recorded.url, **kwargs)
        except httpx.RequestError as exc:
            raise ConnectionException(str(exc)) from exc
        response = Response.from_httpx(raw, request=recorded)
        self._write_sink(response)
        return response

    async def _send_httpx_async(self, recorded: RecordedRequest) -> Response:
        client_kwargs, kwargs = self._httpx_kwargs(recorded)
        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                raw = await client.request(recorded.method, recorded.url, **kwargs)
        except httpx.RequestError as exc:
            raise ConnectionException(str(exc)) from exc
        response = Response.from_httpx(raw, request=recorded)
        self._write_sink(response)
        return response
