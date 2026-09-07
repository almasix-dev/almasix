"""M20 HTTP Client — façade, pending request, responses, fakes, retry, pool."""

from __future__ import annotations

import io
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from avalon.client import (
    ConnectionException,
    Factory,
    Http,
    HttpClientException,
    OutOfFakeResponses,
    PendingRequest,
    PendingRequestException,
    Pool,
    RecordedRequest,
    RequestException,
    Response,
    Sequence,
    StrayRequestException,
    get_factory,
    http,
    http_assert_sent,
    http_fake,
    http_get,
    http_post,
    set_factory,
)
from avalon.client.provider import ClientServiceProvider
from avalon.debug import DumpAndDie
from avalon.framework.application import Application
from avalon.support.collection import Collection

URL = "https://api.example.test/users"


@pytest.fixture(autouse=True)
def fresh_factory() -> Iterator[Factory]:
    """Every test starts with a pristine, process-wide factory."""
    factory = Factory()
    set_factory(factory)
    yield factory
    set_factory(None)


def transport(handler: Callable[[httpx.Request], httpx.Response]) -> dict[str, Any]:
    """Options that route live httpx calls through a mock transport."""
    return {"transport": httpx.MockTransport(handler)}


def ok_handler(payload: Any = None, status: int = 200) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(status, json=payload if payload is not None else {"ok": True})

    return handler


# --- Response ---------------------------------------------------------------


def test_response_bodies_accept_bytes_str_json_and_none() -> None:
    assert Response(200, None).content() == b""
    assert Response(200, b"raw").content() == b"raw"
    assert Response(200, "text").body() == "text"
    assert Response(200, {"a": 1}).json() == {"a": 1}


def test_response_make_sets_json_content_type_for_structures() -> None:
    made = Response.make({"a": 1}, 201)
    assert made.status() == 201
    assert made.header("content-type") == "application/json"
    assert Response.make("plain").body() == "plain"
    assert Response.make().content() == b""
    assert Response.make([1, 2]).json() == [1, 2]


def test_response_from_httpx_copies_status_headers_cookies_and_url() -> None:
    raw = httpx.Response(
        201,
        json={"id": 1},
        headers={"X-Trace": "abc", "Set-Cookie": "sid=42; Path=/"},
        request=httpx.Request("GET", URL),
    )
    response = Response.from_httpx(raw, request="recorded")
    assert response.status() == 201
    assert response.json("id") == 1
    assert response.header("X-Trace") == "abc"
    assert response.cookies() == {"sid": "42"}
    assert response.url() == URL
    assert response.request() == "recorded"


def test_response_from_httpx_tolerates_unreadable_cookie_jar() -> None:
    raw = SimpleNamespace(
        status_code=200,
        content=b"{}",
        headers={},
        url=URL,
        cookies=object(),
        reason_phrase="OK",
    )
    assert Response.from_httpx(raw).cookies() == {}
    assert Response.from_httpx(raw).reason() == "OK"


def test_response_from_httpx_without_reason_phrase() -> None:
    raw = SimpleNamespace(status_code=200, content=b"", headers={}, url=URL, cookies=None)
    assert Response.from_httpx(raw).reason() == ""


def test_response_json_is_cached_and_survives_invalid_bodies() -> None:
    response = Response(200, '{"name": "Ada"}')
    assert response.json() == {"name": "Ada"}
    assert response.json("name") == "Ada"
    assert response.json("missing", "fallback") == "fallback"
    assert Response(200, "   ").json() is None
    assert Response(200, "not json").json() is None
    assert Response(200, "[1, 2]").json("key", "fallback") == "fallback"


def test_response_object_and_collect() -> None:
    assert Response(200, {"name": "Ada"}).object().name == "Ada"
    assert [item.id for item in Response(200, [{"id": 1}, {"id": 2}]).object()] == [1, 2]
    assert Response(200, "[1, 2]").object() == [1, 2]
    assert Response(200, '"scalar"').object() == "scalar"
    assert Response(200, [{"id": 1}]).collect() == Collection([{"id": 1}])
    assert Response(200, None).collect() == Collection([])


def test_response_status_predicates() -> None:
    assert Response(200).ok() and Response(200).successful()
    assert Response(301).redirect()
    assert Response(404).failed() and Response(404).client_error()
    assert Response(503).failed() and Response(503).server_error()
    assert Response(401).unauthorized()
    assert Response(403).forbidden()
    assert Response(404).not_found()
    assert Response(410).gone()
    assert Response(429).too_many_requests()
    assert Response(201).created()
    assert Response(202).accepted()
    assert Response(204).no_content()
    assert not Response(200).failed()


def test_response_metadata_accessors() -> None:
    response = Response(200, "body", {"X-Trace": "1"}, {"sid": "9"}, URL, "OK", "req")
    assert response.headers() == {"X-Trace": "1"}
    assert response.header("missing", "default") == "default"
    assert response.cookies() == {"sid": "9"}
    assert response.effective_uri() == URL
    assert response.reason() == "OK"
    assert response.request() == "req"
    assert repr(response) == f"<Response 200 {URL}>"


def test_response_dict_protocol() -> None:
    response = Response(200, {"name": "Ada"})
    assert response["name"] == "Ada"
    assert "name" in response
    assert bool(response) is True
    assert bool(Response(500)) is False
    assert "name" not in Response(200, "[1]")
    with pytest.raises(KeyError):
        _ = Response(200, "[1]")["name"]


def test_response_on_error_runs_only_for_failures() -> None:
    seen: list[int] = []
    Response(200).on_error(lambda r: seen.append(r.status()))
    assert seen == []
    Response(500).on_error(lambda r: seen.append(r.status()))
    assert seen == [500]


def test_response_throw_variants() -> None:
    assert Response(200).throw().ok()
    with pytest.raises(RequestException) as excinfo:
        Response(500, {"error": "boom"}).throw()
    assert "500" in str(excinfo.value)

    assert Response(500).throw_if(False).status() == 500
    assert Response(200).throw_if(True).ok()
    with pytest.raises(RequestException):
        Response(500).throw_if(True)
    with pytest.raises(RequestException):
        Response(500).throw_if(lambda r: r.server_error())

    assert Response(500).throw_unless(True).status() == 500
    with pytest.raises(RequestException):
        Response(500).throw_unless(False)
    with pytest.raises(RequestException):
        Response(500).throw_unless(lambda r: r.ok())


def test_response_throw_by_status() -> None:
    assert Response(200).throw_if_status(403).ok()
    with pytest.raises(RequestException):
        Response(403).throw_if_status(403)
    with pytest.raises(RequestException):
        Response(403).throw_if_status(lambda status: status >= 400)
    assert Response(200).throw_unless_status(200).ok()
    with pytest.raises(RequestException):
        Response(500).throw_unless_status(200)


def test_response_throw_accepts_a_callback() -> None:
    seen: list[int] = []
    assert Response(200).throw(lambda r: seen.append(r.status())).ok()
    with pytest.raises(RequestException):
        Response(500).throw(lambda r: seen.append(r.status()))
    assert seen == [500]


def test_response_with_request_copies_and_tags() -> None:
    stub = Response.make({"ok": True})
    recorded = RecordedRequest(method="GET", url=URL)
    tagged = stub.with_request(recorded)
    assert tagged is not stub
    assert tagged.request() is recorded
    assert tagged.url() == URL
    assert stub.url() == ""
    assert stub.with_request(SimpleNamespace()).url() == ""


# --- RecordedRequest --------------------------------------------------------


def test_recorded_request_accessors() -> None:
    recorded = RecordedRequest(
        method="POST",
        url="https://api.example.test/users?page=1&tag=a&tag=b&flag=",
        headers={"Content-Type": "application/json"},
        data={"name": "Ada"},
    )
    assert recorded.path == "/users"
    assert recorded.header("content-type") == "application/json"
    assert recorded.header("missing", "default") == "default"
    assert recorded.has_header("Content-Type")
    assert not recorded.has_header("X-Nope")
    assert recorded.is_json()
    assert recorded.data_get("name") == "Ada"
    assert recorded.data_get("missing", "default") == "default"
    assert "name" in recorded
    assert recorded["name"] == "Ada"
    assert recorded.query() == {"page": "1", "tag": ["a", "b"], "flag": ""}
    assert recorded.query("page") == "1"
    assert recorded.query("tag") == ["a", "b"]
    assert recorded.query("missing", "default") == "default"


def test_recorded_request_without_json_body() -> None:
    recorded = RecordedRequest(method="GET", url="https://api.example.test", data="raw")
    assert recorded.path == "/"
    assert not recorded.is_json()
    assert recorded.data_get("name", "default") == "default"
    assert "name" not in recorded
    with pytest.raises(KeyError):
        _ = recorded["name"]


# --- Exceptions -------------------------------------------------------------


def test_exception_hierarchy_and_forwarding() -> None:
    stray = StrayRequestException("GET", URL)
    assert isinstance(stray, HttpClientException)
    assert stray.method == "GET"
    assert stray.url == URL
    assert URL in str(stray)

    failure = RequestException(Response(422, {"errors": {"name": "required"}}))
    assert failure.response.status() == 422
    assert failure.status() == 422
    assert failure.json("errors") == {"name": "required"}

    assert isinstance(OutOfFakeResponses(), HttpClientException)
    assert isinstance(PendingRequestException(), HttpClientException)
    assert isinstance(ConnectionException(), HttpClientException)


# --- Factory + fakes --------------------------------------------------------


def test_factory_fake_without_callback_returns_empty_200() -> None:
    Http.fake()
    response = Http.get(URL)
    assert response.status() == 200
    assert response.body() == ""
    assert get_factory().is_faking()


def test_factory_fake_with_url_map() -> None:
    Http.fake(
        {
            "https://api.example.test/users": Http.response({"users": []}),
            "https://api.example.test/*": Http.response(None, 500),
        }
    )
    assert Http.get(URL).json() == {"users": []}
    assert Http.get("https://api.example.test/other").status() == 500


def test_factory_fake_with_callable_receives_recorded_request() -> None:
    Http.fake(lambda request: Http.response({"url": request.url, "method": request.method}))
    assert Http.post(URL, {"n": 1}).json() == {"url": URL, "method": "POST"}


def test_factory_fake_with_plain_value_and_status_shortcuts() -> None:
    Http.fake({"*": 503})
    assert Http.get(URL).status() == 503

    set_factory(Factory())
    Http.fake({"*": {"ok": True}})
    assert Http.get(URL).json() == {"ok": True}


def test_factory_fake_with_a_single_response_stub() -> None:
    Http.fake(Http.response({"single": True}, 202))
    assert Http.get(URL).status() == 202
    assert Http.post("https://api.example.test/other").json() == {"single": True}


def test_factory_fake_can_raise_configured_exception() -> None:
    Http.fake({"*": ConnectionException("dns failure")})
    with pytest.raises(ConnectionException, match="dns failure"):
        Http.get(URL)


def test_factory_stub_url_matches_host_path_and_wildcards() -> None:
    Http.stub_url("api.example.test/*", Http.response({"matched": "host-path"}))
    assert Http.get(URL).json() == {"matched": "host-path"}

    set_factory(Factory())
    Http.stub_url("/users", Http.response({"matched": "path"}))
    assert Http.get(URL).json() == {"matched": "path"}

    set_factory(Factory())
    Http.stub_url("api.example.test", Http.response({"matched": "host"}))
    assert Http.get(URL).json() == {"matched": "host"}

    set_factory(Factory())
    Http.stub_url("https://api.example.test/users?*", Http.response({"matched": "prefix"}))
    assert Http.get(URL, {"page": 2}).json() == {"matched": "prefix"}


def test_factory_stub_that_does_not_match_falls_through_to_empty_200() -> None:
    Http.fake({"https://other.test/*": Http.response({"nope": True})})
    assert Http.get(URL).body() == ""


def test_factory_prevent_stray_requests() -> None:
    Http.fake({"https://other.test/*": Http.response({"ok": True})})
    Http.prevent_stray_requests()
    with pytest.raises(StrayRequestException):
        Http.get(URL)
    assert Http.recorded() == []

    Http.allow_stray_requests()
    assert Http.get(URL).status() == 200


def test_factory_match_stub_is_inert_until_faking(fresh_factory: Factory) -> None:
    fresh_factory.prevent_stray_requests(False)
    assert fresh_factory.match_stub(RecordedRequest(method="GET", url=URL)) is None
    assert not fresh_factory.is_faking()
    assert not fresh_factory.stray_prevented()


def test_sequence_pops_queued_responses_then_falls_back_to_empty() -> None:
    Http.fake_sequence().push({"id": 1}).push_status(500).push_response(Http.response("third"))
    assert Http.get(URL).json() == {"id": 1}
    assert Http.get(URL).status() == 500
    assert Http.get(URL).body() == "third"
    assert Http.get(URL).status() == 200


def test_sequence_when_empty_accepts_response_or_callable() -> None:
    Http.fake_sequence().push({"id": 1}).when_empty(Http.response({"done": True}))
    assert Http.get(URL).json() == {"id": 1}
    assert Http.get(URL).json() == {"done": True}

    set_factory(Factory())
    Http.fake_sequence().when_empty(lambda request: Http.response({"url": request.url}))
    assert Http.get(URL).json() == {"url": URL}


def test_sequence_fail_when_empty_and_dont_fail_when_empty() -> None:
    sequence = Http.fake_sequence().push({"id": 1}).fail_when_empty()
    assert Http.get(URL).json() == {"id": 1}
    with pytest.raises(OutOfFakeResponses):
        Http.get(URL)
    sequence.dont_fail_when_empty()
    assert Http.get(URL).status() == 200

    set_factory(Factory())
    Http.fake_sequence().when_empty(Http.response("x")).dont_fail_when_empty()
    assert Http.get(URL).body() == "x"


def test_sequence_can_be_scoped_to_a_url_and_passed_to_fake() -> None:
    Http.fake_sequence("https://api.example.test/users").push({"scoped": True})
    assert Http.get(URL).json() == {"scoped": True}
    assert Http.get("https://api.example.test/other").body() == ""

    set_factory(Factory())
    Http.fake(Sequence().push({"direct": True}))
    assert Http.get(URL).json() == {"direct": True}


def test_assert_sequences_are_empty() -> None:
    Http.fake_sequence().push({"id": 1}).push({"id": 2})
    Http.get(URL)
    with pytest.raises(AssertionError, match="queued fake responses"):
        Http.assert_sequences_are_empty()
    Http.get(URL)
    Http.assert_sequences_are_empty()


def test_recording_and_assertions() -> None:
    Http.fake()
    Http.get(URL)
    Http.post("https://api.example.test/orders", {"name": "Ada"})

    assert len(Http.recorded()) == 2
    assert [r.method for r in Http.recorded(lambda r: r.method == "POST")] == ["POST"]

    Http.assert_sent("https://api.example.test/users")
    Http.assert_sent(lambda r: r.method == "POST" and r["name"] == "Ada")
    Http.assert_not_sent("https://evil.test/*")
    Http.assert_sent_count(2)
    Http.assert_sent_in_order(
        ["https://api.example.test/users", "https://api.example.test/orders"]
    )
    http_assert_sent("https://api.example.test/orders")


def test_assertion_failures_are_reported() -> None:
    Http.fake()
    Http.assert_nothing_sent()
    Http.get(URL)

    with pytest.raises(AssertionError, match="was not recorded"):
        Http.assert_sent("https://evil.test/*")
    with pytest.raises(AssertionError, match="unexpected request"):
        Http.assert_not_sent(URL)
    with pytest.raises(AssertionError, match="Expected 5 requests, recorded 1"):
        Http.assert_sent_count(5)
    with pytest.raises(AssertionError):
        Http.assert_nothing_sent()
    with pytest.raises(AssertionError, match="expected order"):
        Http.assert_sent_in_order(["https://api.example.test/orders", URL])


def test_factory_globals_seed_every_pending_request(fresh_factory: Factory) -> None:
    fresh_factory.with_headers({"X-App": "avalon"})
    fresh_factory.with_options({"follow_redirects": False})
    fresh_factory.base_url("https://api.example.test")
    Http.fake()

    Http.get("/users")
    recorded = Http.recorded()[0]
    assert recorded.url == URL
    assert recorded.header("X-App") == "avalon"
    assert fresh_factory.global_headers() == {"X-App": "avalon"}


def test_factory_global_middleware_wraps_requests_and_responses() -> None:
    Http.global_request_middleware(lambda request: _tag(request, "global"))
    Http.global_response_middleware(lambda response: Response.make({"rewritten": True}))
    Http.fake({"*": Http.response({"original": True})})

    assert Http.get(URL).json() == {"rewritten": True}
    assert Http.recorded()[0].header("X-Tag") == "global"
    assert len(get_factory().request_middleware()) == 1
    assert len(get_factory().response_middleware()) == 1


def test_factory_middleware_may_return_none_to_keep_the_original() -> None:
    Http.global_request_middleware(lambda request: None)
    Http.global_response_middleware(lambda response: None)
    Http.fake({"*": Http.response({"kept": True})})
    assert Http.get(URL).json() == {"kept": True}


# --- PendingRequest fluency -------------------------------------------------


def test_fluent_setters_never_mutate_the_source_request() -> None:
    base = Http.pending()
    configured = (
        base.with_headers({"X-One": 1})
        .with_header("X-Two", 2)
        .with_query_parameters({"page": 1})
        .with_url_parameters({"id": 7})
        .with_cookies({"sid": "a"})
        .with_cookie("other", "b")
        .with_options({"follow_redirects": False})
        .with_middleware(lambda request: request)
        .with_request_middleware(lambda request: request)
        .with_response_middleware(lambda response: response)
        .before_sending(lambda request: None)
        .timeout(5)
        .connect_timeout(2)
        .retry(3, 10)
        .base_url("https://api.example.test/")
        .sink(io.BytesIO())
    )
    assert base.headers == {}
    assert configured.headers == {"X-One": "1", "X-Two": "2"}
    assert configured._base_url == "https://api.example.test"
    assert configured._tries == 3
    assert configured._retry_delay == pytest.approx(0.01)


def test_header_helpers() -> None:
    assert Http.with_token("secret").headers["Authorization"] == "Bearer secret"
    assert Http.with_token("secret", "Token").headers["Authorization"] == "Token secret"
    assert Http.with_user_agent("avalon/1").headers["User-Agent"] == "avalon/1"
    assert Http.accept("text/csv").headers["Accept"] == "text/csv"
    assert Http.accept_json().headers["Accept"] == "application/json"
    assert Http.content_type("text/plain").headers["Content-Type"] == "text/plain"
    replaced = Http.with_header("X-Keep", "1").replace_headers({"X-Only": "2"})
    assert replaced.headers == {"X-Only": "2"}


def test_body_format_helpers_and_validation() -> None:
    assert Http.as_json().headers["Content-Type"] == "application/json"
    assert Http.as_form().headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert "Content-Type" not in Http.as_json().as_multipart().headers
    assert Http.body_format("body")._body_format == "body"
    with pytest.raises(PendingRequestException, match="Unknown body format"):
        Http.body_format("xml")


def test_auth_helpers() -> None:
    assert Http.with_basic_auth("user", "pass")._auth == ("user", "pass")
    assert isinstance(Http.with_digest_auth("user", "pass")._auth, httpx.DigestAuth)


def test_when_and_unless_apply_configuration_conditionally() -> None:
    with_token = Http.when(True, lambda request: request.with_token("yes"))
    assert with_token.headers["Authorization"] == "Bearer yes"
    assert Http.when(False, lambda request: request.with_token("no")).headers == {}
    assert (
        Http.when(False, lambda r: r, lambda request: request.with_token("default")).headers[
            "Authorization"
        ]
        == "Bearer default"
    )
    assert Http.when(lambda request: True, lambda r: r.with_token("callable")).headers[
        "Authorization"
    ] == "Bearer callable"
    assert Http.unless(False, lambda request: request.with_token("unless")).headers[
        "Authorization"
    ] == "Bearer unless"
    assert Http.unless(lambda request: True, lambda r: r.with_token("no")).headers == {}


def test_dump_and_dd_expose_the_pending_configuration(
    capsys: pytest.CaptureFixture[str],
) -> None:
    pending = Http.base_url("https://api.example.test").timeout(3).dump()
    assert isinstance(pending, PendingRequest)
    assert "base_url" in capsys.readouterr().err

    Http.dump("explicit")
    assert "explicit" in capsys.readouterr().err

    with pytest.raises(DumpAndDie):
        Http.dd()
    with pytest.raises(DumpAndDie):
        Http.dd("explicit")


# --- URL building + payload encoding ---------------------------------------


def test_url_parameters_base_url_and_query_merging() -> None:
    Http.fake()
    Http.base_url("https://api.example.test").with_url_parameters({"id": 7}).get(
        "/users/{id}?tag=a", {"page": 2}
    )
    assert Http.recorded()[0].url == "https://api.example.test/users/7?tag=a&page=2"

    Http.base_url("https://api.example.test").get("https://other.test/absolute")
    assert Http.recorded()[1].url == "https://other.test/absolute"


def test_dict_and_list_payloads_default_to_json() -> None:
    Http.fake()
    Http.post(URL, {"name": "Ada"})
    recorded = Http.recorded()[0]
    assert recorded.body == '{"name": "Ada"}'
    assert recorded.header("Content-Type") == "application/json"

    Http.post(URL, [1, 2])
    assert Http.recorded()[1].body == "[1, 2]"


def test_form_bytes_and_scalar_payload_encoding() -> None:
    Http.fake()
    Http.as_form().post(URL, {"name": "Ada", "tags": ["a", "b"]})
    assert Http.recorded()[0].body == "name=Ada&tags=a&tags=b"

    Http.as_form().post(URL, "already=encoded")
    assert Http.recorded()[1].body == "already=encoded"

    Http.post(URL, b"bytes")
    assert Http.recorded()[2].body == b"bytes"

    Http.post(URL, 42)
    assert Http.recorded()[3].body == "42"

    Http.with_body("raw override").post(URL, {"ignored": True})
    assert Http.recorded()[4].body == "raw override"


def test_accept_and_global_headers_are_defaults_not_overrides() -> None:
    get_factory().with_headers({"X-App": "avalon", "Accept": "text/html"})
    Http.fake()
    Http.accept("text/csv").with_header("X-App", "mine").get(URL)
    recorded = Http.recorded()[0]
    assert recorded.header("Accept") == "text/csv"
    assert recorded.header("X-App") == "mine"


def test_attach_switches_to_multipart_and_records_files() -> None:
    Http.fake()
    Http.attach("photo", b"binary", "me.jpg").post(URL)
    assert Http.recorded()[0].files == {"photo": ("me.jpg", b"binary")}

    Http.attach("doc", b"pdf", headers={"Content-Type": "application/pdf"}).post(URL)
    assert Http.recorded()[1].files == {
        "doc": ("doc", b"pdf", None, {"Content-Type": "application/pdf"})
    }


def _tag(request: RecordedRequest, value: str) -> RecordedRequest:
    request.headers["X-Tag"] = value
    return request


def test_request_middleware_and_before_sending_hooks_see_the_recorded_request() -> None:
    seen: list[str] = []
    Http.fake()
    (
        Http.with_middleware(lambda request: _tag(request, "middleware"))
        .before_sending(lambda request: seen.append(request.header("X-Tag") or ""))
        .get(URL)
    )
    assert seen == ["middleware"]
    assert Http.recorded()[0].header("X-Tag") == "middleware"


# --- Verbs, async, and live httpx -------------------------------------------


def test_every_sync_verb_is_recorded() -> None:
    Http.fake()
    Http.get(URL, {"page": 1})
    Http.head(URL, {"page": 1})
    Http.post(URL, {"n": 1})
    Http.put(URL, {"n": 1})
    Http.patch(URL, {"n": 1})
    Http.delete(URL)
    Http.options(URL)
    Http.send("TRACE", URL)
    assert [r.method for r in Http.recorded()] == [
        "GET",
        "HEAD",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
        "TRACE",
    ]


async def test_every_async_verb_is_recorded() -> None:
    Http.fake()
    assert (await Http.aget(URL, {"page": 1})).ok()
    assert (await Http.ahead(URL, {"page": 1})).ok()
    assert (await Http.apost(URL, {"n": 1})).ok()
    assert (await Http.aput(URL, {"n": 1})).ok()
    assert (await Http.apatch(URL, {"n": 1})).ok()
    assert (await Http.adelete(URL)).ok()
    assert (await Http.aoptions(URL)).ok()
    assert [r.method for r in Http.recorded()] == [
        "GET",
        "HEAD",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ]


async def test_async_stray_requests_are_prevented_too() -> None:
    Http.fake({"https://other.test/*": Http.response({})})
    Http.prevent_stray_requests()
    with pytest.raises(StrayRequestException):
        await Http.aget(URL)


async def test_async_fake_falls_through_to_empty_200() -> None:
    Http.fake({"https://other.test/*": Http.response({})})
    assert (await Http.aget(URL)).body() == ""


def test_live_request_goes_through_httpx() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Trace"] == "1"
        assert request.headers["Cookie"] == "sid=42"
        return httpx.Response(200, json={"echo": str(request.url)})

    response = (
        Http.with_options(transport(handler))
        .with_headers({"X-Trace": "1"})
        .with_cookies({"sid": "42"})
        .with_basic_auth("user", "pass")
        .get(URL)
    )
    assert response.json() == {"echo": URL}
    assert Http.recorded()[0].url == URL


async def test_live_async_request_goes_through_httpx() -> None:
    response = await Http.with_options(transport(ok_handler())).aget(URL)
    assert response.json() == {"ok": True}


def test_live_request_sends_json_form_multipart_and_raw_bodies() -> None:
    seen: list[tuple[str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.headers.get("content-type", ""), request.content))
        return httpx.Response(200)

    options = transport(handler)
    Http.with_options(options).post(URL, {"name": "Ada"})
    Http.with_options(options).as_form().post(URL, {"name": "Ada"})
    Http.with_options(options).as_form().post(URL, "name=Ada")
    Http.with_options(options).attach("photo", b"binary", "me.jpg").post(URL, {"name": "Ada"})
    Http.with_options(options).with_body("raw").post(URL)
    Http.with_options(options).attach("photo", b"binary", "me.jpg").post(URL, "ignored")

    assert seen[0][0] == "application/json"
    assert seen[1][0] == "application/x-www-form-urlencoded"
    assert seen[1][1] == b"name=Ada"
    assert seen[2][1] == b"name=Ada"
    assert seen[3][0].startswith("multipart/form-data")
    assert b"me.jpg" in seen[3][1] and b"Ada" in seen[3][1]
    assert seen[4][1] == b"raw"
    assert seen[5][0].startswith("multipart/form-data")
    assert b"ignored" not in seen[5][1]


def test_option_split_between_client_and_request_kwargs() -> None:
    """No transport configured: options land on the client, body on the request."""
    pending = Http.timeout(5).connect_timeout(1).with_cookies({"sid": "42"})
    client_kwargs, request_kwargs = pending._httpx_kwargs(
        RecordedRequest(method="GET", url=URL, cookies={"sid": "42"})
    )
    assert "transport" not in client_kwargs
    assert client_kwargs["cookies"] == {"sid": "42"}
    assert client_kwargs["timeout"].read == 5
    assert client_kwargs["timeout"].connect == 1
    assert request_kwargs["follow_redirects"] is True


def test_live_request_honours_follow_redirects_option() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/users":
            return httpx.Response(302, headers={"Location": "/moved"})
        return httpx.Response(200, json={"moved": True})

    options = transport(handler)
    assert Http.with_options(options).get(URL).json() == {"moved": True}
    assert Http.with_options({**options, "follow_redirects": False}).get(URL).status() == 302


def test_transport_errors_become_connection_exceptions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ConnectionException, match="refused"):
        Http.with_options(transport(handler)).get(URL)


async def test_async_transport_errors_become_connection_exceptions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ConnectionException, match="refused"):
        await Http.with_options(transport(handler)).aget(URL)


def test_sink_writes_to_a_stream_or_path(tmp_path: Path) -> None:
    stream = io.BytesIO()
    Http.with_options(transport(ok_handler())).sink(stream).get(URL)
    assert b'"ok"' in stream.getvalue()

    destination = tmp_path / "body.json"
    Http.with_options(transport(ok_handler())).sink(destination).get(URL)
    assert b'"ok"' in destination.read_bytes()


async def test_async_sink_writes_the_body(tmp_path: Path) -> None:
    destination = tmp_path / "async.json"
    await Http.with_options(transport(ok_handler())).sink(destination).aget(URL)
    assert b'"ok"' in destination.read_bytes()


# --- Retry ------------------------------------------------------------------


def test_retry_counts_total_attempts_and_returns_the_first_success() -> None:
    Http.fake_sequence().push_status(500).push_status(500).push({"ok": True})
    response = Http.retry(3).get(URL)
    assert response.json() == {"ok": True}
    Http.assert_sent_count(3)


def test_retry_raises_request_exception_once_attempts_are_exhausted() -> None:
    Http.fake({"*": Http.response({"error": "down"}, 500)})
    with pytest.raises(RequestException):
        Http.retry(2).get(URL)
    Http.assert_sent_count(2)


def test_retry_with_throw_false_returns_the_last_failure() -> None:
    Http.fake({"*": Http.response({"error": "down"}, 503)})
    response = Http.retry(2, throw=False).get(URL)
    assert response.status() == 503
    Http.assert_sent_count(2)


def test_retry_when_narrows_which_failures_are_retried() -> None:
    Http.fake({"*": Http.response(None, 404)})
    response = Http.retry(3, when=lambda error: error.server_error(), throw=False).get(URL)
    assert response.not_found()
    Http.assert_sent_count(1)

    set_factory(Factory())
    seen: list[tuple[Any, PendingRequest]] = []

    def retry_all(error: Any, request: PendingRequest) -> bool:
        seen.append((error, request))
        return True

    Http.fake_sequence().push_status(500).push({"ok": True})
    assert Http.retry(2, when=retry_all).get(URL).json() == {"ok": True}
    assert seen[0][0].status() == 500
    assert isinstance(seen[0][1], PendingRequest)


def test_retry_when_may_accept_varargs() -> None:
    Http.fake_sequence().push_status(500).push({"ok": True})
    assert Http.retry(2, when=lambda *_args: True).get(URL).json() == {"ok": True}
    Http.assert_sent_count(2)


def test_retry_recovers_from_connection_failures() -> None:
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 3:
            raise httpx.ConnectError("flaky", request=request)
        return httpx.Response(200, json={"ok": True})

    response = Http.with_options(transport(handler)).retry(3, 1).get(URL)
    assert response.json() == {"ok": True}
    assert len(attempts) == 3


def test_retry_reraises_connection_failure_after_the_last_attempt() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("always down", request=request)

    with pytest.raises(ConnectionException, match="always down"):
        Http.with_options(transport(handler)).retry(2).get(URL)


def test_retry_when_can_refuse_to_retry_connection_failures() -> None:
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        raise httpx.ConnectError("nope", request=request)

    with pytest.raises(ConnectionException):
        (
            Http.with_options(transport(handler))
            .retry(3, when=lambda error: not isinstance(error, ConnectionException))
            .get(URL)
        )
    assert len(attempts) == 1


def test_retry_of_one_attempt_is_a_plain_send() -> None:
    Http.fake({"*": Http.response(None, 500)})
    assert Http.retry(0, throw=False).get(URL).status() == 500
    Http.assert_sent_count(1)


async def test_async_retry_sleeps_between_attempts() -> None:
    Http.fake_sequence().push_status(500).push({"ok": True})
    assert (await Http.retry(2, 1).aget(URL)).json() == {"ok": True}
    Http.assert_sent_count(2)


async def test_async_retry_raises_after_exhausting_attempts() -> None:
    Http.fake({"*": Http.response(None, 500)})
    with pytest.raises(RequestException):
        await Http.retry(2).aget(URL)


async def test_async_retry_reraises_connection_failures() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("async down", request=request)

    with pytest.raises(ConnectionException, match="async down"):
        await Http.with_options(transport(handler)).retry(2).aget(URL)


# --- Throwing ---------------------------------------------------------------


def test_throw_raises_for_failures_and_passes_successes_through() -> None:
    Http.fake({"*": Http.response({"error": "boom"}, 500)})
    with pytest.raises(RequestException):
        Http.throw().get(URL)

    set_factory(Factory())
    Http.fake({"*": Http.response({"ok": True})})
    assert Http.throw().get(URL).json() == {"ok": True}


def test_throw_callback_runs_exactly_once_before_raising() -> None:
    seen: list[int] = []
    Http.fake({"*": Http.response(None, 422)})
    with pytest.raises(RequestException):
        Http.throw(lambda response: seen.append(response.status())).get(URL)
    assert seen == [422]


def test_throw_if_and_throw_unless_gate_on_a_condition() -> None:
    Http.fake({"*": Http.response(None, 500)})
    assert Http.throw_if(False).get(URL).status() == 500
    with pytest.raises(RequestException):
        Http.throw_if(True).get(URL)
    with pytest.raises(RequestException):
        Http.throw_if(lambda response: response.server_error()).get(URL)
    assert Http.throw_unless(True).get(URL).status() == 500
    with pytest.raises(RequestException):
        Http.throw_unless(False).get(URL)
    with pytest.raises(RequestException):
        Http.throw_unless(lambda response: response.ok()).get(URL)


def test_response_middleware_runs_before_the_throw_policy() -> None:
    Http.fake({"*": Http.response(None, 500)})
    response = Http.with_response_middleware(lambda _r: Response.make({"healed": True})).throw().get(
        URL
    )
    assert response.json() == {"healed": True}


# --- Pool -------------------------------------------------------------------


def test_pool_runs_indexed_and_named_requests_in_order() -> None:
    Http.fake(lambda request: Http.response({"url": request.url, "method": request.method}))
    responses = Http.pool(
        lambda pool: (
            pool.get("https://api.example.test/a"),
            pool.as_("users").get(URL),
            pool.head("https://api.example.test/b"),
            pool.post("https://api.example.test/c", {"n": 1}),
            pool.put("https://api.example.test/d", {"n": 1}),
            pool.patch("https://api.example.test/e", {"n": 1}),
            pool.delete("https://api.example.test/f"),
            pool.options("https://api.example.test/g"),
            pool.send("TRACE", "https://api.example.test/h"),
        )
    )
    assert list(responses) == [0, "users", 1, 2, 3, 4, 5, 6, 7]
    assert responses["users"].json()["url"] == URL
    assert responses[2].json()["method"] == "POST"
    Http.assert_sent_count(9)


def test_pool_with_no_requests_returns_nothing() -> None:
    assert Http.pool(lambda pool: pool) == {}
    assert Pool(get_factory()).run() == {}


def test_pool_queries_are_forwarded() -> None:
    Http.fake()
    responses = Http.pool(lambda pool: pool.get(URL, {"page": 2}))
    assert responses[0].ok()
    assert Http.recorded()[0].query("page") == "2"


# --- Façade delegation, helpers, provider -----------------------------------


FLUENT_DELEGATIONS: list[tuple[str, tuple[Any, ...]]] = [
    ("with_headers", ({"X": "1"},)),
    ("with_header", ("X", "1")),
    ("replace_headers", ({"X": "1"},)),
    ("with_token", ("secret",)),
    ("with_user_agent", ("avalon",)),
    ("with_basic_auth", ("user", "pass")),
    ("with_digest_auth", ("user", "pass")),
    ("with_url_parameters", ({"id": 1},)),
    ("with_query_parameters", ({"page": 1},)),
    ("with_cookies", ({"sid": "1"},)),
    ("with_cookie", ("sid", "1")),
    ("timeout", (5,)),
    ("connect_timeout", (2,)),
    ("retry", (2,)),
    ("with_options", ({"follow_redirects": True},)),
    ("with_middleware", (lambda request: request,)),
    ("with_request_middleware", (lambda request: request,)),
    ("with_response_middleware", (lambda response: response,)),
    ("before_sending", (lambda request: None,)),
    ("as_json", ()),
    ("as_form", ()),
    ("as_multipart", ()),
    ("body_format", ("json",)),
    ("content_type", ("text/plain",)),
    ("accept", ("text/plain",)),
    ("accept_json", ()),
    ("attach", ("photo", b"x")),
    ("with_body", ("raw",)),
    ("sink", (io.BytesIO(),)),
    ("base_url", ("https://api.example.test",)),
    ("throw", ()),
    ("throw_if", (True,)),
    ("throw_unless", (True,)),
]


@pytest.mark.parametrize(("name", "args"), FLUENT_DELEGATIONS, ids=[n for n, _ in FLUENT_DELEGATIONS])
def test_facade_fluent_methods_delegate_to_a_pending_request(
    name: str, args: tuple[Any, ...]
) -> None:
    assert isinstance(getattr(Http, name)(*args), PendingRequest)


def test_facade_exposes_factory_state() -> None:
    assert isinstance(Http.factory(), Factory)
    assert isinstance(Http.pending(), PendingRequest)
    assert Http.response({"a": 1}, 201).status() == 201
    assert isinstance(Http.fake(), Factory)
    assert isinstance(Http.fake_sequence(), Sequence)
    assert isinstance(Http.stub_url(URL, Http.response()), Factory)
    assert isinstance(Http.prevent_stray_requests(), Factory)
    assert isinstance(Http.allow_stray_requests(), Factory)
    assert isinstance(Http.global_request_middleware(lambda request: request), Factory)
    assert isinstance(Http.global_response_middleware(lambda response: response), Factory)


def test_get_factory_creates_a_singleton_on_demand() -> None:
    set_factory(None)
    factory = get_factory()
    assert get_factory() is factory
    assert http() is factory


def test_module_helpers_mirror_the_facade() -> None:
    assert isinstance(http_fake({"*": Http.response({"ok": True})}), Factory)
    assert http_get(URL, {"page": 1}).json() == {"ok": True}
    assert http_post(URL, {"n": 1}).json() == {"ok": True}
    http_assert_sent(URL)


def test_provider_binds_the_factory_into_the_container(tmp_path: Path) -> None:
    app = Application(tmp_path)
    provider = ClientServiceProvider(app)
    provider.register()
    bound = app.container.resolve(Factory)
    assert isinstance(bound, Factory)
    assert app.container.resolve("http") is bound
    assert get_factory() is bound

    set_factory(None)
    provider.boot()
    assert get_factory() is bound


def test_provider_boot_falls_back_to_the_process_factory(tmp_path: Path) -> None:
    app = Application(tmp_path)
    factory = get_factory()
    ClientServiceProvider(app).boot()
    assert get_factory() is factory
