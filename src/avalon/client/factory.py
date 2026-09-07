"""HTTP client factory — fakes, sequences, recording, global options."""

from __future__ import annotations

import fnmatch
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlsplit

from avalon.client.exceptions import OutOfFakeResponses
from avalon.client.pending import PendingRequest
from avalon.client.request import RecordedRequest
from avalon.client.response import Response


class Sequence:
    """Queued fake responses (Laravel ``Http::fakeSequence()``)."""

    def __init__(self) -> None:
        self._responses: list[Any] = []
        self._empty: Any = None
        self._fail_when_empty = False

    def push(self, body: Any = None, status: int = 200, headers: dict[str, str] | None = None) -> Sequence:
        self._responses.append(Response.make(body, status, headers))
        return self

    def push_status(self, status: int, headers: dict[str, str] | None = None) -> Sequence:
        return self.push(None, status, headers)

    def push_response(self, response: Any) -> Sequence:
        self._responses.append(response)
        return self

    def when_empty(self, response: Any) -> Sequence:
        self._empty = response
        self._fail_when_empty = False
        return self

    def dont_fail_when_empty(self) -> Sequence:
        self._fail_when_empty = False
        if self._empty is None:
            self._empty = Response.make(None, 200)
        return self

    def fail_when_empty(self) -> Sequence:
        self._fail_when_empty = True
        return self

    def is_empty(self) -> bool:
        return not self._responses

    def __call__(self, request: RecordedRequest) -> Any:
        if self._responses:
            return self._responses.pop(0)
        if self._fail_when_empty:
            raise OutOfFakeResponses(f"No more fake responses for {request.method} {request.url}")
        if self._empty is not None:
            empty = self._empty
            return empty(request) if callable(empty) and not isinstance(empty, Response) else empty
        return Response.make(None, 200)


class Factory:
    """Creates pending requests and holds fake / recording state."""

    def __init__(self) -> None:
        self._stubs: list[tuple[Callable[[RecordedRequest], bool], Any]] = []
        self._recorded: list[RecordedRequest] = []
        self._faking = False
        self._prevent_stray = False
        self._global_headers: dict[str, str] = {}
        self._global_options: dict[str, Any] = {}
        self._request_middleware: list[Callable[[RecordedRequest], RecordedRequest]] = []
        self._response_middleware: list[Callable[[Response], Response]] = []
        self._default_base_url = ""

    def pending(self) -> PendingRequest:
        request = PendingRequest(self)
        if self._global_headers:
            request = request.with_headers(self._global_headers)
        if self._global_options:
            request = request.with_options(self._global_options)
        if self._default_base_url:
            request = request.base_url(self._default_base_url)
        return request

    def base_url(self, url: str) -> Factory:
        self._default_base_url = url
        return self

    def global_request_middleware(
        self, middleware: Callable[[RecordedRequest], RecordedRequest]
    ) -> Factory:
        self._request_middleware.append(middleware)
        return self

    def global_response_middleware(self, middleware: Callable[[Response], Response]) -> Factory:
        self._response_middleware.append(middleware)
        return self

    def with_headers(self, headers: Mapping[str, Any]) -> Factory:
        self._global_headers.update({str(k): str(v) for k, v in headers.items()})
        return self

    def with_options(self, options: Mapping[str, Any]) -> Factory:
        self._global_options.update(dict(options))
        return self

    def request_middleware(self) -> list[Callable[[RecordedRequest], RecordedRequest]]:
        return list(self._request_middleware)

    def response_middleware(self) -> list[Callable[[Response], Response]]:
        return list(self._response_middleware)

    def global_headers(self) -> dict[str, str]:
        return dict(self._global_headers)

    def is_faking(self) -> bool:
        return self._faking

    def stray_prevented(self) -> bool:
        return self._prevent_stray

    def fake(self, callback: Any = None) -> Factory:
        """Fake every request, a URL map, a sequence, a callable, or a single response."""
        self._faking = True
        if callback is None:
            self._stubs.append((lambda _req: True, Response.make(None, 200)))
        elif isinstance(callback, Mapping):
            for pattern, response in callback.items():
                self._stubs.append((_url_matcher(str(pattern)), response))
        else:
            self._stubs.append((lambda _req: True, callback))
        return self

    def fake_sequence(self, urls: str | None = None) -> Sequence:
        sequence = Sequence()
        self._faking = True
        matcher = _url_matcher(urls) if urls else (lambda _req: True)
        self._stubs.append((matcher, sequence))
        return sequence

    def stub_url(self, url: str, callback: Any) -> Factory:
        self._faking = True
        self._stubs.append((_url_matcher(url), callback))
        return self

    def prevent_stray_requests(self, prevent: bool = True) -> Factory:
        self._prevent_stray = prevent
        return self

    def allow_stray_requests(self) -> Factory:
        self._prevent_stray = False
        return self

    def match_stub(self, request: RecordedRequest) -> Any | None:
        if not self._faking:
            return None
        for matcher, handler in self._stubs:
            if matcher(request):
                return handler
        return None

    def record(self, request: RecordedRequest) -> None:
        self._recorded.append(request)

    def recorded(
        self, callback: Callable[[RecordedRequest], bool] | None = None
    ) -> list[RecordedRequest]:
        if callback is None:
            return list(self._recorded)
        return [req for req in self._recorded if callback(req)]

    def assert_sent(
        self,
        callback: str | Callable[[RecordedRequest], bool],
    ) -> None:
        matcher = _as_request_predicate(callback)
        if not any(matcher(req) for req in self._recorded):
            raise AssertionError("An expected request was not recorded.")

    def assert_not_sent(
        self,
        callback: str | Callable[[RecordedRequest], bool],
    ) -> None:
        matcher = _as_request_predicate(callback)
        if any(matcher(req) for req in self._recorded):
            raise AssertionError("An unexpected request was recorded.")

    def assert_sent_in_order(
        self, callbacks: list[str | Callable[[RecordedRequest], bool]]
    ) -> None:
        remaining = list(self._recorded)
        for callback in callbacks:
            matcher = _as_request_predicate(callback)
            found_at = next((i for i, req in enumerate(remaining) if matcher(req)), None)
            if found_at is None:
                raise AssertionError("Requests were not recorded in the expected order.")
            remaining = remaining[found_at + 1 :]

    def assert_sent_count(self, count: int) -> None:
        actual = len(self._recorded)
        if actual != count:
            raise AssertionError(f"Expected {count} requests, recorded {actual}.")

    def assert_nothing_sent(self) -> None:
        self.assert_sent_count(0)

    def assert_sequences_are_empty(self) -> None:
        for _matcher, handler in self._stubs:
            if isinstance(handler, Sequence) and not handler.is_empty():
                raise AssertionError("Not all queued fake responses were consumed.")


def _url_matcher(pattern: str) -> Callable[[RecordedRequest], bool]:
    def matches(request: RecordedRequest) -> bool:
        url = request.url
        parsed = urlsplit(url)
        host_only = parsed.netloc
        without_query = urlunsplit_no_query(parsed)
        candidates = [url, without_query, host_only, parsed.path, f"{host_only}{parsed.path}"]
        for candidate in candidates:
            if fnmatch.fnmatch(candidate, pattern) or candidate == pattern:
                return True
        return pattern.endswith("*") and any(c.startswith(pattern[:-1]) for c in candidates)

    return matches


def urlunsplit_no_query(parsed: Any) -> str:
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}" if parsed.scheme else parsed.path


def _as_request_predicate(
    callback: str | Callable[[RecordedRequest], bool],
) -> Callable[[RecordedRequest], bool]:
    if callable(callback) and not isinstance(callback, str):
        return callback
    matcher = _url_matcher(str(callback))
    return matcher
