"""M20 Laravel parity — events, batching, macros, URI templates, retry policies."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from avalon.client import (
    Batch,
    BatchInProgressException,
    ConnectionException,
    ConnectionFailed,
    Factory,
    Http,
    PendingRequest,
    Pool,
    RecordedRequest,
    RequestException,
    RequestSending,
    Response,
    ResponseReceived,
    set_factory,
)
from avalon.client.uri_template import expand
from avalon.events import Dispatcher, Event, set_dispatcher

URL = "https://api.example.test/users"
OTHER = "https://api.example.test/orders"


@pytest.fixture(autouse=True)
def fresh_factory() -> Iterator[Factory]:
    factory = Factory()
    set_factory(factory)
    yield factory
    set_factory(None)


@pytest.fixture(autouse=True)
def fresh_dispatcher() -> Iterator[Dispatcher]:
    dispatcher = Dispatcher()
    set_dispatcher(dispatcher)
    yield dispatcher
    set_dispatcher(None)


@pytest.fixture(autouse=True)
def restore_truncation() -> Iterator[None]:
    original = RequestException._truncate_at
    yield
    RequestException._truncate_at = original


def transport(handler: Any) -> dict[str, Any]:
    return {"transport": httpx.MockTransport(handler)}


def ok_handler(payload: Any = None) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json=payload if payload is not None else {"ok": True})

    return handler


# --- Events -----------------------------------------------------------------


def test_request_sending_and_response_received_are_dispatched() -> None:
    seen: list[Any] = []
    Event.listen(RequestSending, lambda event: seen.append(event))
    Event.listen(ResponseReceived, lambda event: seen.append(event))
    Http.fake({"*": Http.response({"ok": True}, 201)})

    Http.post(URL, {"name": "Ada"})

    sending, received = seen
    assert isinstance(sending, RequestSending)
    assert sending.request.url == URL
    assert sending.request["name"] == "Ada"
    assert isinstance(received, ResponseReceived)
    assert received.request.method == "POST"
    assert received.response.status() == 201


def test_connection_failed_is_dispatched_when_no_response_arrives() -> None:
    seen: list[ConnectionFailed] = []
    Event.listen(ConnectionFailed, lambda event: seen.append(event))

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ConnectionException):
        Http.with_options(transport(handler)).get(URL)

    assert seen[0].request.url == URL
    assert isinstance(seen[0].exception, ConnectionException)


async def test_async_dispatches_the_same_events() -> None:
    seen: list[Any] = []
    Event.listen(ResponseReceived, lambda event: seen.append(event))
    Event.listen(ConnectionFailed, lambda event: seen.append(event))

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    Http.fake({"https://api.example.test/users": Http.response({"ok": True})})
    await Http.aget(URL)
    with pytest.raises(ConnectionException):
        await Http.with_options(transport(handler)).aget("https://elsewhere.test")

    assert isinstance(seen[0], ResponseReceived)
    assert isinstance(seen[1], ConnectionFailed)


# --- Recording request / response pairs -------------------------------------


def test_recorded_returns_request_and_response_pairs() -> None:
    Http.fake({URL: Http.response(status=500), OTHER: Http.response({"ok": True})})
    Http.get(URL)
    Http.get(OTHER)

    recorded = Http.recorded()
    request, response = recorded[0]
    assert request.url == URL
    assert response.status() == 500
    assert recorded[1][1].successful()


def test_recorded_and_assertions_accept_a_response_argument() -> None:
    Http.fake({URL: Http.response(status=500), OTHER: Http.response({"ok": True})})
    Http.get(URL)
    Http.get(OTHER)

    filtered = Http.recorded(lambda request, response: response.successful())
    assert [request.url for request, _response in filtered] == [OTHER]

    Http.assert_sent(lambda request, response: request.url == URL and response.status() == 500)
    Http.assert_not_sent(lambda request, response: response.status() == 404)
    Http.assert_sent_in_order(
        [
            lambda request, response: response.server_error(),
            lambda request, response: response.ok(),
        ]
    )


def test_failed_connections_are_not_recorded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ConnectionException):
        Http.with_options(transport(handler)).get(URL)
    assert Http.recorded() == []


# --- Fake helpers -----------------------------------------------------------


def test_failed_connection_stub() -> None:
    Http.fake({"api.example.test/*": Http.failed_connection("dns is down")})
    with pytest.raises(ConnectionException, match="dns is down"):
        Http.get(URL)
    assert isinstance(Http.failed_connection(), ConnectionException)


def test_failed_request_stub_carries_the_response() -> None:
    Http.fake({"*": Http.failed_request({"code": "not_found"}, 404)})
    with pytest.raises(RequestException) as excinfo:
        Http.get(URL)
    assert excinfo.value.response.status() == 404
    assert excinfo.value.json("code") == "not_found"
    assert excinfo.value.response.request().url == URL


# --- Global options and macros ---------------------------------------------


def test_global_options_seed_every_request() -> None:
    seen: list[bool] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(True)
        return httpx.Response(200, json={"ok": True})

    Http.global_options(transport(handler))
    assert Http.get(URL).json() == {"ok": True}
    assert seen == [True]


def test_macros_configure_reusable_request_paths() -> None:
    Http.macro(
        "github",
        lambda: Http.with_headers({"X-Example": "example"}).base_url("https://github.com"),
    )
    Http.fake({"github.com/*": Http.response({"repos": []})})

    assert Http.github().get("/repos").json() == {"repos": []}
    request, _response = Http.recorded()[0]
    assert request.url == "https://github.com/repos"
    assert request.header("X-Example") == "example"


def test_macros_can_take_arguments_and_be_flushed() -> None:
    Http.macro("service", lambda name: Http.base_url(f"https://{name}.test"))
    Http.fake()
    Http.service("billing").get("/invoices")
    assert Http.recorded()[0][0].url == "https://billing.test/invoices"

    Http.flush_macros()
    with pytest.raises(AttributeError, match="macro 'service'"):
        Http.service("billing")
    with pytest.raises(AttributeError):
        _ = Http.not_a_macro


# --- Exception truncation ---------------------------------------------------


def test_request_exception_message_carries_a_truncated_body() -> None:
    long_body = "x" * 200
    exception = RequestException(Response.make(long_body, 500))
    assert "status code 500" in str(exception)
    assert "x" * 120 in str(exception)
    assert "x" * 121 not in str(exception)
    assert str(exception).endswith("...\n")


def test_request_exception_truncation_is_configurable() -> None:
    RequestException.truncate_at(10)
    assert "0123456789..." in str(RequestException(Response.make("0123456789abc", 500)))

    RequestException.dont_truncate()
    assert "0123456789abc" in str(RequestException(Response.make("0123456789abc", 500)))


def test_truncate_exceptions_at_applies_per_request() -> None:
    Http.fake({"*": Http.response("0123456789abcdef", 500)})
    with pytest.raises(RequestException) as excinfo:
        Http.truncate_exceptions_at(4).throw().get(URL)
    assert "0123..." in str(excinfo.value)
    assert "456" not in str(excinfo.value)


# --- Raw bodies and recorded request inspection -----------------------------


def test_with_body_accepts_a_content_type() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    Http.with_options(transport(handler)).with_body("Zm9v", "image/jpeg").post(URL)
    assert seen[0].headers["content-type"] == "image/jpeg"
    assert seen[0].content == b"Zm9v"


def test_recorded_request_content_type_helpers() -> None:
    Http.fake()
    Http.as_json().post(URL, {"name": "Ada"})
    Http.as_form().post(URL, {"name": "Ada"})
    Http.attach("photo", b"binary", "me.jpg").post(URL)

    as_json, as_form, multipart = (request for request, _response in Http.recorded())
    assert as_json.is_json() and not as_json.is_form() and not as_json.is_multipart()
    assert as_form.is_form() and not as_form.is_json()
    assert multipart.is_multipart()
    assert multipart.has_file() and multipart.has_file("photo")
    assert not multipart.has_file("missing")
    assert not as_json.has_file()
    assert as_json.has_header("Content-Type", "application/json")
    assert not as_json.has_header("Content-Type", "text/plain")
    assert not as_json.has_header("X-Missing", "value")


def test_multipart_content_type_is_recognized_from_the_header() -> None:
    request = RecordedRequest(
        method="POST", url=URL, headers={"Content-Type": "multipart/form-data; boundary=x"}
    )
    assert request.is_multipart()


# --- Retry policies ---------------------------------------------------------


def test_retry_sleep_may_be_a_callable() -> None:
    delays: list[tuple[int, Any]] = []

    def backoff(attempt: int, error: Any) -> float:
        delays.append((attempt, error))
        return 0

    Http.fake_sequence().push_status(500).push_status(500).push({"ok": True})
    assert Http.retry(3, backoff).get(URL).json() == {"ok": True}
    assert [attempt for attempt, _error in delays] == [1, 2]
    assert isinstance(delays[0][1], RequestException)


def test_retry_sleep_callable_may_take_only_the_attempt() -> None:
    attempts: list[int] = []
    Http.fake_sequence().push_status(500).push({"ok": True})
    assert Http.retry(2, lambda attempt: attempts.append(attempt) or 0).get(URL).ok()
    assert attempts == [1]


def test_retry_accepts_a_list_of_delays_as_the_first_argument() -> None:
    Http.fake_sequence().push_status(500).push_status(500).push({"ok": True})
    assert Http.retry([1, 1]).get(URL).json() == {"ok": True}
    Http.assert_sent_count(3)


def test_retry_accepts_a_list_of_delays_as_the_sleep_argument() -> None:
    Http.fake_sequence().push_status(500).push({"ok": True})
    assert Http.retry(2, [1]).get(URL).ok()
    Http.assert_sent_count(2)

    set_factory(Factory())
    Http.fake_sequence().push_status(500).push({"ok": True})
    assert Http.retry(2, []).get(URL).ok()


def test_retry_when_receives_a_request_exception_for_failed_responses() -> None:
    seen: list[Any] = []
    Http.fake({"*": Http.response({"error": "nope"}, 503)})

    def only_connection_errors(error: Any) -> bool:
        seen.append(error)
        return isinstance(error, ConnectionException)

    response = Http.retry(3, when=only_connection_errors, throw=False).get(URL)
    assert response.status() == 503
    assert isinstance(seen[0], RequestException)
    assert seen[0].response.json("error") == "nope"
    Http.assert_sent_count(1)


def test_retry_callback_can_reconfigure_the_next_attempt() -> None:
    def refresh_token(error: Any, request: PendingRequest) -> bool:
        if error.response.status() != 401:
            return False
        request.with_token("fresh")
        return True

    Http.fake_sequence().push_status(401).push({"ok": True})
    response = Http.with_token("stale").retry(2, 0, refresh_token).get(URL)

    assert response.json() == {"ok": True}
    first, second = (request for request, _response in Http.recorded())
    assert first.header("Authorization") == "Bearer stale"
    assert second.header("Authorization") == "Bearer fresh"


def test_retry_view_does_not_leak_into_the_original_request() -> None:
    Http.fake_sequence().push_status(500).push({"ok": True})
    pending = Http.with_token("stale").retry(2, 0, _swap_token)
    pending.get(URL)
    assert pending.headers["Authorization"] == "Bearer stale"


def _swap_token(_error: Any, request: PendingRequest) -> bool:
    request.with_token("fresh")
    return True


# --- URI templates ----------------------------------------------------------


def test_url_parameters_expand_the_laravel_documented_template() -> None:
    Http.fake()
    Http.with_url_parameters(
        {
            "endpoint": "https://laravel.com",
            "page": "docs",
            "version": "12.x",
            "topic": "validation",
        }
    ).get("{+endpoint}/{page}/{version}/{topic}")
    assert Http.recorded()[0][0].url == "https://laravel.com/docs/12.x/validation"


def test_simple_expansion_percent_encodes_reserved_characters() -> None:
    assert expand("{value}", {"value": "https://laravel.com"}) == "https%3A%2F%2Flaravel.com"
    assert expand("{+value}", {"value": "https://laravel.com"}) == "https://laravel.com"
    assert expand("{#value}", {"value": "a/b"}) == "#a/b"


def test_expansion_operators() -> None:
    variables = {"var": "value", "x": "1024", "y": "768", "empty": "", "list": ["a", "b"]}
    assert expand("{x,y}", variables) == "1024,768"
    assert expand("{.x,y}", variables) == ".1024.768"
    assert expand("/path{/var}", variables) == "/path/value"
    assert expand("{;x,y}", variables) == ";x=1024;y=768"
    assert expand("{?x,y}", variables) == "?x=1024&y=768"
    assert expand("{&x}", variables) == "&x=1024"
    assert expand("{;empty}", variables) == ";empty"
    assert expand("{?empty}", variables) == "?empty="
    assert expand("{list}", variables) == "a,b"
    assert expand("{?list}", variables) == "?list=a,b"


def test_explode_and_prefix_modifiers() -> None:
    variables = {"list": ["a", "b"], "keys": {"one": 1, "two": 2}, "var": "value"}
    assert expand("{/list*}", variables) == "/a/b"
    assert expand("{?list*}", variables) == "?list=a&list=b"
    assert expand("{keys}", variables) == "one,1,two,2"
    assert expand("{?keys}", variables) == "?keys=one,1,two,2"
    assert expand("{?keys*}", variables) == "?one=1&two=2"
    assert expand("{var:3}", variables) == "val"


def test_expansion_skips_missing_and_empty_values() -> None:
    assert expand("{missing}", {}) == ""
    assert expand("x{missing}y", {"missing": None}) == "xy"
    assert expand("{empty_list}", {"empty_list": []}) == ""
    assert expand("{empty_map}", {"empty_map": {}}) == ""
    assert expand("{?empty_list*}", {"empty_list": []}) == ""
    assert expand("{flag}", {"flag": True}) == "true"
    assert expand("{flag}", {"flag": False}) == "false"
    assert expand("{count}", {"count": 7}) == "7"


def test_plain_braces_are_left_alone_without_url_parameters() -> None:
    Http.fake()
    Http.get("https://api.example.test/{unexpanded}")
    assert Http.recorded()[0][0].url == "https://api.example.test/{unexpanded}"


# --- Pool -------------------------------------------------------------------


def test_pool_accepts_a_concurrency_limit() -> None:
    Http.fake({"*": Http.response({"ok": True})})
    responses = Http.pool(
        lambda pool: [pool.get(f"https://api.example.test/{n}") for n in range(4)],
        concurrency=2,
    )
    assert len(responses) == 4
    assert all(response.ok() for response in responses.values())

    set_factory(Factory())
    Http.fake({"*": Http.response({"ok": True})})
    assert len(Http.pool(lambda pool: pool.concurrency(1).get(URL))) == 1


def test_pool_requests_can_be_customized_individually() -> None:
    Http.fake({"*": Http.response({"ok": True})})
    responses = Http.pool(
        lambda pool: [
            pool.with_headers({"X-Example": "example"}).get(URL),
            pool.as_("named").with_token("secret").accept_json().get(OTHER),
            pool.request().with_header("X-Third", "3").get(URL),
        ]
    )
    assert responses[0].ok() and responses["named"].ok()

    by_url = {(request.url, request.header("X-Example")) for request, _r in Http.recorded()}
    assert (URL, "example") in by_url
    tokens = [request.header("Authorization") for request, _r in Http.recorded()]
    assert "Bearer secret" in tokens
    assert any(request.header("X-Third") == "3" for request, _r in Http.recorded())


def test_pool_exposes_client_failures_as_values() -> None:
    Http.fake(
        {
            URL: Http.failed_connection("down"),
            OTHER: Http.response({"ok": True}),
        }
    )
    responses = Http.pool(lambda pool: [pool.get(URL), pool.get(OTHER)])
    assert isinstance(responses[0], ConnectionException)
    assert responses[1].ok()


def test_pool_propagates_programming_errors() -> None:
    def explode(_request: RecordedRequest) -> Response:
        raise ValueError("bug in the stub")

    Http.fake(explode)
    with pytest.raises(ValueError, match="bug in the stub"):
        Http.pool(lambda pool: pool.get(URL))


def test_pool_reads_pending_attributes_through_the_proxy() -> None:
    pool = Pool(Http.factory())
    assert pool.request().headers == {}
    # Members that are not fluent setters pass straight through.
    assert pool.request().with_token("secret")._debug_payload()["headers"] == {
        "Authorization": "Bearer secret"
    }
    with pytest.raises(AttributeError):
        _ = pool._not_a_real_attribute


# --- Batching ---------------------------------------------------------------


def test_batch_runs_requests_and_fires_callbacks_in_order() -> None:
    Http.fake({"*": Http.response({"ok": True})})
    events: list[str] = []
    progressed: list[str | int] = []

    batch = (
        Http.batch(
            lambda batch: [
                batch.get(URL),
                batch.as_("orders").get(OTHER),
            ]
        )
        .before(lambda batch: events.append(f"before:{batch.total_requests}"))
        .progress(lambda batch, key, response: progressed.append(key))
        .then(lambda batch, results: events.append(f"then:{len(results)}"))
        .catch(lambda batch, key, response: events.append("catch"))
        .finally_(lambda batch, results: events.append("finally"))
    )
    assert batch.pending_requests == 2
    results = batch.send()

    assert list(results) == [0, "orders"]
    assert results["orders"].json() == {"ok": True}
    assert events == ["before:2", "then:2", "finally"]
    assert sorted(progressed, key=str) == [0, "orders"]


def test_batch_inspection_reflects_progress_and_failures() -> None:
    Http.fake({URL: Http.response(status=500), OTHER: Http.response({"ok": True})})
    caught: list[Any] = []

    batch = Http.batch(lambda batch: [batch.as_("bad").get(URL), batch.as_("good").get(OTHER)])
    batch.catch(lambda batch, key, outcome: caught.append((key, outcome)))
    batch.then(lambda batch, results: caught.append("then"))

    assert batch.total_requests == 2
    assert not batch.finished()
    results = batch.send()

    assert batch.finished()
    assert batch.processed_requests() == 2
    assert batch.pending_requests == 0
    assert batch.failed_requests == 1
    assert batch.has_failures()
    assert [key for key, _outcome in caught] == ["bad"]
    assert "then" not in caught
    assert results["bad"].status() == 500
    assert batch.results()["good"].ok()


def test_batch_treats_client_exceptions_as_failures() -> None:
    Http.fake({"*": Http.failed_connection("down")})
    caught: list[Any] = []
    batch = Http.batch(lambda batch: batch.get(URL)).catch(
        lambda batch, key, outcome: caught.append(outcome)
    )
    results = batch.send()
    assert isinstance(results[0], ConnectionException)
    assert isinstance(caught[0], ConnectionException)
    assert batch.has_failures()


def test_batch_rejects_new_requests_once_sent() -> None:
    Http.fake()
    batch = Http.batch(lambda batch: batch.get(URL))
    batch.send()
    with pytest.raises(BatchInProgressException, match="cannot be added"):
        batch.get(OTHER)
    with pytest.raises(BatchInProgressException, match="already been sent"):
        batch.send()


def test_batch_concurrency_and_empty_batches() -> None:
    Http.fake()
    assert Http.batch(lambda batch: batch.concurrency(2).get(URL)).send()[0].ok()

    empty = Http.batch(lambda batch: batch)
    assert empty.send() == {}
    assert empty.finished()
    assert empty.total_requests == 0

    deferred_empty = Http.batch(lambda batch: batch)
    assert deferred_empty.defer().wait(timeout=5) == {}
    assert deferred_empty.finished()


def test_deferred_batches_run_in_the_background() -> None:
    Http.fake({"*": Http.response({"ok": True})})
    finished = threading.Event()
    batch = Http.batch(lambda batch: [batch.get(URL), batch.get(OTHER)]).finally_(
        lambda batch, results: finished.set()
    )

    assert batch.defer() is batch
    results = batch.wait(timeout=5)

    assert finished.wait(timeout=5)
    assert len(results) == 2
    assert batch.finished()


def test_batch_reads_pending_attributes_through_the_proxy() -> None:
    batch = Batch(Http.factory())
    assert batch.request().headers == {}
    assert batch.wait(timeout=0) == {}
    with pytest.raises(AttributeError):
        _ = batch._not_a_real_attribute
