"""``Http`` façade — Laravel-shaped HTTP client entry point."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from almasix.client.batch import Batch
from almasix.client.exceptions import ConnectionException, HttpClientException, RequestException
from almasix.client.factory import Factory, Sequence
from almasix.client.pending import PendingRequest
from almasix.client.pool import Pool
from almasix.client.request import RecordedRequest
from almasix.client.response import Response

_factory: Factory | None = None


def get_factory() -> Factory:
    global _factory
    if _factory is None:
        _factory = Factory()
    return _factory


def set_factory(factory: Factory | None) -> None:
    global _factory
    _factory = factory


class _HttpMeta(type):
    """Resolves ``Http.macro(...)`` names registered on the factory."""

    def __getattr__(cls, name: str) -> Any:
        factory = get_factory()
        if factory.has_macro(name):
            return factory.macro_for(name)
        raise AttributeError(f"{cls.__name__} has no attribute or macro {name!r}")


class Http(metaclass=_HttpMeta):
    """Static façade over the HTTP client factory."""

    @classmethod
    def factory(cls) -> Factory:
        return get_factory()

    @classmethod
    def macro(cls, name: str, callback: Callable[..., Any]) -> Factory:
        return cls.factory().macro(name, callback)

    @classmethod
    def flush_macros(cls) -> Factory:
        return cls.factory().flush_macros()

    @classmethod
    def pending(cls) -> PendingRequest:
        return cls.factory().pending()

    @classmethod
    def response(
        cls,
        body: Any = None,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> Response:
        return Response.make(body, status, headers)

    @classmethod
    def fake(cls, callback: Any = None) -> Factory:
        return cls.factory().fake(callback)

    @classmethod
    def fake_sequence(cls, urls: str | None = None) -> Sequence:
        return cls.factory().fake_sequence(urls)

    @classmethod
    def sequence(cls) -> Sequence:
        """An unattached sequence, for use inside a ``fake`` URL map."""
        return Sequence()

    @classmethod
    def failed_connection(cls, message: str = "Connection failed.") -> ConnectionException:
        return ConnectionException(message)

    @classmethod
    def failed_request(
        cls,
        body: Any = None,
        status: int = 500,
        headers: dict[str, str] | None = None,
    ) -> RequestException:
        return RequestException(Response.make(body, status, headers))

    @classmethod
    def stub_url(cls, url: str, callback: Any) -> Factory:
        return cls.factory().stub_url(url, callback)

    @classmethod
    def prevent_stray_requests(cls, prevent: bool = True) -> Factory:
        return cls.factory().prevent_stray_requests(prevent)

    @classmethod
    def allow_stray_requests(cls, patterns: list[str] | None = None) -> Factory:
        return cls.factory().allow_stray_requests(patterns)

    @classmethod
    def recorded(
        cls, callback: Callable[..., bool] | None = None
    ) -> list[tuple[RecordedRequest, Response]]:
        return cls.factory().recorded(callback)

    @classmethod
    def assert_sent(cls, callback: str | Callable[..., bool]) -> None:
        cls.factory().assert_sent(callback)

    @classmethod
    def assert_not_sent(cls, callback: str | Callable[..., bool]) -> None:
        cls.factory().assert_not_sent(callback)

    @classmethod
    def assert_sent_in_order(cls, callbacks: list[str | Callable[..., bool]]) -> None:
        cls.factory().assert_sent_in_order(callbacks)

    @classmethod
    def assert_sent_count(cls, count: int) -> None:
        cls.factory().assert_sent_count(count)

    @classmethod
    def assert_nothing_sent(cls) -> None:
        cls.factory().assert_nothing_sent()

    @classmethod
    def assert_sequences_are_empty(cls) -> None:
        cls.factory().assert_sequences_are_empty()

    @classmethod
    def global_request_middleware(
        cls, middleware: Callable[[RecordedRequest], RecordedRequest]
    ) -> Factory:
        return cls.factory().global_request_middleware(middleware)

    @classmethod
    def global_response_middleware(cls, middleware: Callable[[Response], Response]) -> Factory:
        return cls.factory().global_response_middleware(middleware)

    @classmethod
    def global_options(cls, options: Mapping[str, Any]) -> Factory:
        return cls.factory().global_options(options)

    @classmethod
    def pool(
        cls, callback: Callable[[Pool], Any], concurrency: int | None = None
    ) -> dict[str | int, Response | HttpClientException]:
        pool = Pool(cls.factory(), concurrency)
        callback(pool)
        return pool.run()

    @classmethod
    def batch(cls, callback: Callable[[Batch], Any]) -> Batch:
        batch = Batch(cls.factory())
        callback(batch)
        return batch

    @classmethod
    def get(cls, url: str, query: Mapping[str, Any] | None = None) -> Response:
        return cls.pending().get(url, query)

    @classmethod
    def head(cls, url: str, query: Mapping[str, Any] | None = None) -> Response:
        return cls.pending().head(url, query)

    @classmethod
    def post(cls, url: str, data: Any = None) -> Response:
        return cls.pending().post(url, data)

    @classmethod
    def put(cls, url: str, data: Any = None) -> Response:
        return cls.pending().put(url, data)

    @classmethod
    def patch(cls, url: str, data: Any = None) -> Response:
        return cls.pending().patch(url, data)

    @classmethod
    def delete(cls, url: str, data: Any = None) -> Response:
        return cls.pending().delete(url, data)

    @classmethod
    def options(cls, url: str, data: Any = None) -> Response:
        return cls.pending().options(url, data)

    @classmethod
    def send(cls, method: str, url: str, data: Any = None) -> Response:
        return cls.pending().send(method, url, data)

    @classmethod
    async def aget(cls, url: str, query: Mapping[str, Any] | None = None) -> Response:
        return await cls.pending().aget(url, query)

    @classmethod
    async def ahead(cls, url: str, query: Mapping[str, Any] | None = None) -> Response:
        return await cls.pending().ahead(url, query)

    @classmethod
    async def apost(cls, url: str, data: Any = None) -> Response:
        return await cls.pending().apost(url, data)

    @classmethod
    async def aput(cls, url: str, data: Any = None) -> Response:
        return await cls.pending().aput(url, data)

    @classmethod
    async def apatch(cls, url: str, data: Any = None) -> Response:
        return await cls.pending().apatch(url, data)

    @classmethod
    async def adelete(cls, url: str, data: Any = None) -> Response:
        return await cls.pending().adelete(url, data)

    @classmethod
    async def aoptions(cls, url: str, data: Any = None) -> Response:
        return await cls.pending().aoptions(url, data)

    @classmethod
    def with_headers(cls, headers: Mapping[str, Any]) -> PendingRequest:
        return cls.pending().with_headers(headers)

    @classmethod
    def with_header(cls, name: str, value: Any) -> PendingRequest:
        return cls.pending().with_header(name, value)

    @classmethod
    def replace_headers(cls, headers: Mapping[str, Any]) -> PendingRequest:
        return cls.pending().replace_headers(headers)

    @classmethod
    def with_token(cls, token: str, type: str = "Bearer") -> PendingRequest:
        return cls.pending().with_token(token, type)

    @classmethod
    def with_user_agent(cls, user_agent: str) -> PendingRequest:
        return cls.pending().with_user_agent(user_agent)

    @classmethod
    def with_basic_auth(cls, username: str, password: str) -> PendingRequest:
        return cls.pending().with_basic_auth(username, password)

    @classmethod
    def with_digest_auth(cls, username: str, password: str) -> PendingRequest:
        return cls.pending().with_digest_auth(username, password)

    @classmethod
    def with_url_parameters(cls, parameters: Mapping[str, Any]) -> PendingRequest:
        return cls.pending().with_url_parameters(parameters)

    @classmethod
    def with_query_parameters(cls, parameters: Mapping[str, Any]) -> PendingRequest:
        return cls.pending().with_query_parameters(parameters)

    @classmethod
    def with_cookies(cls, cookies: Mapping[str, str]) -> PendingRequest:
        return cls.pending().with_cookies(cookies)

    @classmethod
    def with_cookie(cls, name: str, value: str) -> PendingRequest:
        return cls.pending().with_cookie(name, value)

    @classmethod
    def timeout(cls, seconds: float) -> PendingRequest:
        return cls.pending().timeout(seconds)

    @classmethod
    def connect_timeout(cls, seconds: float) -> PendingRequest:
        return cls.pending().connect_timeout(seconds)

    @classmethod
    def retry(
        cls,
        times: int | list[float],
        sleep: float | list[float] | Callable[..., float] = 0,
        when: Callable[..., bool] | None = None,
        throw: bool = True,
    ) -> PendingRequest:
        return cls.pending().retry(times, sleep, when, throw)

    @classmethod
    def with_options(cls, options: Mapping[str, Any]) -> PendingRequest:
        return cls.pending().with_options(options)

    @classmethod
    def with_middleware(cls, middleware: Callable) -> PendingRequest:
        return cls.pending().with_middleware(middleware)

    @classmethod
    def with_request_middleware(cls, middleware: Callable) -> PendingRequest:
        return cls.pending().with_request_middleware(middleware)

    @classmethod
    def with_response_middleware(cls, middleware: Callable) -> PendingRequest:
        return cls.pending().with_response_middleware(middleware)

    @classmethod
    def before_sending(cls, callback: Callable) -> PendingRequest:
        return cls.pending().before_sending(callback)

    @classmethod
    def as_json(cls) -> PendingRequest:
        return cls.pending().as_json()

    @classmethod
    def as_form(cls) -> PendingRequest:
        return cls.pending().as_form()

    @classmethod
    def as_multipart(cls) -> PendingRequest:
        return cls.pending().as_multipart()

    @classmethod
    def body_format(cls, format: str) -> PendingRequest:
        return cls.pending().body_format(format)

    @classmethod
    def content_type(cls, content_type: str) -> PendingRequest:
        return cls.pending().content_type(content_type)

    @classmethod
    def accept(cls, content_type: str) -> PendingRequest:
        return cls.pending().accept(content_type)

    @classmethod
    def accept_json(cls) -> PendingRequest:
        return cls.pending().accept_json()

    @classmethod
    def attach(
        cls,
        name: str,
        contents: Any,
        filename: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> PendingRequest:
        return cls.pending().attach(name, contents, filename, headers)

    @classmethod
    def with_body(cls, content: Any, content_type: str | None = None) -> PendingRequest:
        return cls.pending().with_body(content, content_type)

    @classmethod
    def truncate_exceptions_at(cls, length: int) -> PendingRequest:
        return cls.pending().truncate_exceptions_at(length)

    @classmethod
    def sink(cls, dest: Any) -> PendingRequest:
        return cls.pending().sink(dest)

    @classmethod
    def base_url(cls, url: str) -> PendingRequest:
        return cls.pending().base_url(url)

    @classmethod
    def throw(cls, callback: Callable | None = None) -> PendingRequest:
        return cls.pending().throw(callback)

    @classmethod
    def throw_if(cls, condition: Any) -> PendingRequest:
        return cls.pending().throw_if(condition)

    @classmethod
    def throw_unless(cls, condition: Any) -> PendingRequest:
        return cls.pending().throw_unless(condition)

    @classmethod
    def when(
        cls, condition: Any, callback: Callable, default: Callable | None = None
    ) -> PendingRequest:
        return cls.pending().when(condition, callback, default)

    @classmethod
    def unless(
        cls, condition: Any, callback: Callable, default: Callable | None = None
    ) -> PendingRequest:
        return cls.pending().unless(condition, callback, default)

    @classmethod
    def dump(cls, *values: Any) -> PendingRequest:
        return cls.pending().dump(*values)

    @classmethod
    def dd(cls, *values: Any) -> None:
        cls.pending().dd(*values)
