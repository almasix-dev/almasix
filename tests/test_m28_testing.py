"""M28 — the testing toolkit, tested with itself.

The application under test is written to a temporary directory once and booted
for each test, because that is what an application's own suite does. Where a
test proves an assertion fails, it asserts on the message: a testing toolkit
whose failures do not explain themselves is worse than none.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from almasix.framework import Application
from almasix.orm import DatabaseManager, Schema, set_manager
from almasix.orm.model import Model
from almasix.orm.soft_deletes import SoftDeletes
from almasix.testing import (
    FakeDisk,
    FakeNotifications,
    FakeQueue,
    PendingCommand,
    TestClient,
    TestResponse,
    assert_database_count,
    assert_database_has,
    assert_database_missing,
    assert_model_exists,
    assert_model_missing,
    assert_not_soft_deleted,
    assert_soft_deleted,
    database_transactions,
    fake,
    fake_disk,
    fake_notifications,
    fake_queue,
    fakeable,
    freeze_time,
    frozen_time,
    restore_fakes,
    smith,
    travel,
    travel_back,
    travel_to,
)
from almasix.testing import TestCase as TestCaseBase
from tests.support import purge_generated_app_modules

pytestmark = pytest.mark.anyio


# --- the application under test ------------------------------------------------


APP_FILES: dict[str, str] = {
    ".env": "APP_NAME=Toolkit\nAPP_KEY=base64:toolkit-testing-key\nAPP_DEBUG=true\n",
    "app/__init__.py": "",
    "app/http/__init__.py": "",
    "app/http/controllers/__init__.py": "",
    "app/models/__init__.py": "",
    "config/app.py": (
        'config = {"name": "Toolkit", "key": "toolkit-testing-key", "debug": True, "providers": []}\n'
    ),
    "config/session.py": (
        'config = {"driver": "cookie", "lifetime": 120, "cookie": "almasix_session", "path": "/"}\n'
    ),
    "config/auth.py": (
        "config = {\n"
        '    "defaults": {"guard": "web"},\n'
        '    "guards": {"web": {"driver": "session", "provider": "users"}},\n'
        '    "providers": {"users": {"driver": "array", "users": []}},\n'
        "}\n"
    ),
    "config/http.py": (
        "config = {\n"
        '    "middleware": [],\n'
        '    "middleware_groups": {\n'
        '        "web": [\n'
        '            "almasix.session.middleware.StartSession",\n'
        '            "almasix.auth.middleware.StartAuth",\n'
        "        ],\n"
        '        "api": [],\n'
        "    },\n"
        '    "middleware_aliases": {\n'
        '        "stamp": "app.http.stamp.Stamp",\n'
        '        "ghost": "app.nowhere.Missing",\n'
        "    },\n"
        "}\n"
    ),
    "config/view.py": 'config = {"paths": ["resources/views"]}\n',
    "app/http/stamp.py": (
        "from almasix.http import Middleware\n"
        "\n"
        "class Stamp(Middleware):\n"
        "    def __init__(self, label='yes'):\n"
        "        self.label = label\n"
        "\n"
        "    async def handle(self, request, call_next):\n"
        "        response = await call_next(request)\n"
        "        response.headers['X-Stamped'] = self.label\n"
        "        return response\n"
    ),
    "resources/views/hello.prism.html": "<h1>Hello {{ name }}</h1>\n<p>Almasix &amp; friends</p>\n",
    "database/migrations/2026_01_01_000000_create_gadgets_table.py": (
        "from almasix.orm import Migration, Schema\n"
        "\n"
        "\n"
        "class CreateGadgetsTable(Migration):\n"
        "    async def up(self) -> None:\n"
        "        await Schema.create(\n"
        "            'gadgets',\n"
        "            lambda table: (\n"
        "                table.id(),\n"
        "                table.string('name'),\n"
        "                table.timestamp('deleted_at').nullable(),\n"
        "            ),\n"
        "        )\n"
        "\n"
        "    async def down(self) -> None:\n"
        "        await Schema.drop_if_exists('gadgets')\n"
    ),
    "routes/__init__.py": "",
    "routes/api.py": "",
    "routes/web.py": (
        "from almasix.http import Request, json, redirect, response\n"
        "from almasix.prism import view\n"
        "from almasix.routing import Route\n"
        "from almasix.session.store import get_session\n"
        "\n"
        "\n"
        "async def hello(request: Request):\n"
        "    return view('hello', {'name': request.query('name', 'world')})\n"
        "\n"
        "\n"
        "async def payload(request: Request):\n"
        "    return {\n"
        "        'ok': True,\n"
        "        'user': {'id': 1, 'name': 'Ada', 'roles': ['author', 'admin']},\n"
        "        'posts': [{'id': 7, 'title': 'Search'}, {'id': 8, 'title': 'Testing'}],\n"
        "    }\n"
        "\n"
        "\n"
        "async def echo(request: Request):\n"
        "    return {'method': request.method, 'input': request.all(), 'sent': request.header('X-Sent')}\n"
        "\n"
        "\n"
        "async def go_away(request: Request):\n"
        "    return redirect('/hello')\n"
        "\n"
        "\n"
        "async def remember(request: Request):\n"
        "    session = get_session()\n"
        "    session.put('seen', request.query('value', 'yes'))\n"
        "    return {'seen': session.get('seen')}\n"
        "\n"
        "\n"
        "async def who(request: Request):\n"
        "    session = get_session()\n"
        "    return {'login': session.get('login_web')}\n"
        "\n"
        "\n"
        "async def invalid(request: Request):\n"
        "    return json({'message': 'The data is invalid.', 'errors': {'email': ['Required.']}}, status=422)\n"
        "\n"
        "\n"
        "async def teapot(request: Request):\n"
        "    return response('short and stout', status=418, headers={'X-Pot': 'tea'})\n"
        "\n"
        "\n"
        "async def download(request: Request):\n"
        "    return response(\n"
        "        'name,id',\n"
        "        headers={'Content-Disposition': 'attachment; filename=\"report.csv\"'},\n"
        "    )\n"
        "\n"
        "\n"
        "async def gone(request: Request):\n"
        "    return response('', status=204)\n"
        "\n"
        "\n"
        "async def boom(request: Request):\n"
        "    return response('', status=500)\n"
        "\n"
        "\n"
        "async def crumbs(request: Request):\n"
        "    return response('ok', headers={'Set-Cookie': 'crumb=chip; Path=/'})\n"
        "\n"
        "\n"
        "with Route.group(middleware=['web']):\n"
        "    Route.get('/hello', hello)\n"
        "    Route.get('/payload', payload)\n"
        "    Route.get('/remember', remember)\n"
        "    Route.get('/who', who)\n"
        "\n"
        "Route.get('/echo', echo)\n"
        "Route.post('/echo', echo)\n"
        "Route.put('/echo', echo)\n"
        "Route.patch('/echo', echo)\n"
        "Route.delete('/echo', echo)\n"
        "Route.get('/go-away', go_away)\n"
        "Route.get('/invalid', invalid)\n"
        "Route.get('/teapot', teapot)\n"
        "Route.get('/download', download)\n"
        "Route.get('/nothing', gone)\n"
        "Route.get('/boom', boom)\n"
        "Route.get('/crumbs', crumbs)\n"
        "\n"
        "with Route.group(middleware=['stamp']):\n"
        "    Route.get('/stamped', echo)\n"
        "\n"
        "with Route.group(middleware=['stamp:loud']):\n"
        "    Route.get('/stamped-loud', echo)\n"
        "\n"
        "with Route.group(middleware=['ghost']):\n"
        "    Route.get('/ghost', echo)\n"
    ),
}


@pytest.fixture
def app_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    purge_generated_app_modules()
    for relative, content in APP_FILES.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delenv("APP_NAME", raising=False)
    yield tmp_path
    purge_generated_app_modules()
    sys.modules.pop("routes.web", None)


@pytest.fixture
def app(app_root: Path) -> Application:
    return Application(app_root).bootstrap()


@pytest.fixture
def client(app: Application) -> TestClient:
    return TestClient(app)


# --- the client -------------------------------------------------------------------


async def test_a_request_goes_through_the_real_stack(client: TestClient) -> None:
    response = await client.get("/hello", params={"name": "Ada"})

    response.assert_ok()
    response.assert_see("Hello Ada")
    response.assert_see_text("Almasix & friends")
    response.assert_dont_see("Goodbye")
    response.assert_view_is("hello")
    response.assert_view_has("name", "Ada")
    response.assert_view_missing("email")
    assert response.status == 200
    assert "Hello" in response.text
    assert response.content.startswith(b"<h1>")
    assert "text/html" in str(response.headers["content-type"])


async def test_every_verb_reaches_its_route(client: TestClient) -> None:
    assert (await client.get("/echo")).json("method") == "GET"
    assert (await client.post("/echo", {"a": "1"})).json("input") == {"a": "1"}
    assert (await client.put("/echo", {"a": "2"})).json("input") == {"a": "2"}
    assert (await client.patch("/echo", {"a": "3"})).json("input") == {"a": "3"}
    assert (await client.delete("/echo")).json("method") == "DELETE"
    assert (await client.options("/echo")).status in {200, 405}
    # Neither OPTIONS nor HEAD is routed unless the application says so.
    assert (await client.head("/echo")).status in {200, 405}


async def test_the_json_verbs_send_and_expect_json(client: TestClient) -> None:
    posted = await client.post_json("/echo", {"title": "Testing"})
    posted.assert_ok().assert_json({"input": {"title": "Testing"}})

    assert (await client.get_json("/echo")).json("method") == "GET"
    assert (await client.put_json("/echo", {"a": 1})).json("input") == {"a": 1}
    assert (await client.patch_json("/echo", {"a": 1})).json("input") == {"a": 1}
    assert (await client.delete_json("/echo")).json("method") == "DELETE"


async def test_headers_cookies_and_tokens_travel_with_the_client(client: TestClient) -> None:
    client.with_header("X-Sent", "first").with_token("abc123").with_cookie("crumb", "yes")
    first = await client.get("/echo")
    assert first.json("sent") == "first"

    client.with_headers({"X-Sent": "second"})
    assert (await client.get("/echo")).json("sent") == "second"

    client.with_basic_auth("ada", "secret")
    client.without_token()
    client.flush_headers()
    assert (await client.get("/echo")).json("sent") is None

    client.with_cookies({"other": "1"})
    assert client.cookies == {"crumb": "yes", "other": "1"}


async def test_a_body_may_be_raw(client: TestClient) -> None:
    response = await client.post("/echo", "just text")

    response.assert_ok()


async def test_a_redirect_is_followed_only_when_asked(client: TestClient) -> None:
    response = await client.get("/go-away")
    response.assert_redirect("/hello")
    response.assert_redirect_contains("hello")
    response.assert_location("/hello")

    followed = await client.following_redirects().get("/go-away")
    followed.assert_ok().assert_see("Hello world")

    client.following_redirects(False)
    assert (await client.get("/go-away", follow_redirects=True)).status == 200


async def test_where_the_request_came_from(client: TestClient) -> None:
    client.from_("/somewhere")

    assert client.headers["Referer"] == "/somewhere"


async def test_the_session_survives_between_requests(client: TestClient) -> None:
    first = await client.get("/remember", params={"value": "one"})
    first.assert_session_has("seen")
    first.assert_session_has("seen", "one")
    first.assert_session_has("seen", lambda value: value.startswith("o"))
    first.assert_session_missing("unset")
    first.assert_session_has_all({"seen": "one"})
    assert first.session("seen") == "one"
    assert "seen" in first.session()

    client.with_session({"seeded": "from the test"})
    second = await client.get("/who")
    second.assert_session_has("seeded", "from the test")

    client.flush_session()
    assert client.session == {}


async def test_acting_as_signs_a_user_in(client: TestClient) -> None:
    class User:
        def get_auth_identifier(self) -> int:
            return 7

        def get_attribute(self, name: str) -> Any:
            return {"email": "ada@example.com", "name": "Ada"}.get(name)

    response = await client.acting_as(User()).get("/who")

    response.assert_ok().assert_json_path("login.id", 7)


async def test_the_client_says_what_it_is(client: TestClient) -> None:
    assert repr(client) == "TestClient(http://localhost)"


# --- the response ------------------------------------------------------------------


async def test_the_status_family(client: TestClient) -> None:
    ok = await client.get("/echo")
    ok.assert_ok().assert_successful().assert_status(200)

    teapot = await client.get("/teapot")
    teapot.assert_status(418).assert_header("X-Pot", "tea").assert_header("X-Pot")
    teapot.assert_header_missing("X-Absent")
    teapot.assert_content("short and stout")
    teapot.assert_streamed_content("short and stout")
    teapot.assert_content_type("text/plain")
    assert teapot.header("X-Pot") == "tea"

    missing = await client.get("/nowhere")
    missing.assert_not_found()

    unprocessable = await client.get("/invalid")
    unprocessable.assert_unprocessable()


async def test_no_content_and_downloads(client: TestClient) -> None:
    (await client.get("/nothing")).assert_no_content()
    download = await client.get("/download")
    download.assert_download().assert_download("report.csv")


async def test_the_json_assertions(client: TestClient) -> None:
    response = await client.get_json("/payload")

    response.assert_json({"ok": True})
    response.assert_json_path("user.name", "Ada")
    response.assert_json_path("user.roles.0", "author")
    response.assert_json_path("user.id", lambda value: value > 0)
    response.assert_json_path("user.id")
    response.assert_json_missing_path("user.password")
    response.assert_json_fragment({"title": "Search"})
    response.assert_json_missing({"title": "Nothing"})
    response.assert_json_count(2, "posts")
    response.assert_json_count(3)
    response.assert_json_structure({"user": ["id", "name"], "posts": {"*": ["id", "title"]}})
    response.assert_json_structure(["ok", "user"])
    response.assert_json_is_object()
    response.assert_json_is_array("posts")
    assert response.json("user.roles") == ["author", "admin"]
    assert response.json("user.missing", "fallback") == "fallback"
    assert response.json()["ok"] is True


async def test_an_exact_json_body(client: TestClient) -> None:
    response = await client.get_json("/echo")

    response.assert_exact_json({"method": "GET", "input": {}, "sent": None})
    response.assert_json({"method": "GET", "input": {}, "sent": None}, strict=True)


async def test_validation_errors_read_from_the_body(client: TestClient) -> None:
    response = await client.get_json("/invalid")

    response.assert_invalid()
    response.assert_invalid("email")
    response.assert_invalid(["email"])
    response.assert_invalid({"email"})
    response.assert_invalid({"email": "Required."})
    response.assert_session_has_errors("email")
    response.assert_valid("name")
    assert response.errors() == {"email": ["Required."]}

    good = await client.get_json("/payload")
    good.assert_valid()
    good.assert_session_has_no_errors()


async def test_a_response_says_what_it_is(client: TestClient) -> None:
    response = await client.get("/echo")

    assert "TestResponse(200 GET" in repr(response)


async def test_dumping_a_response_prints_it(
    client: TestClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (await client.get("/teapot")).dump()

    printed = capsys.readouterr().out
    assert "HTTP 418" in printed
    assert "short and stout" in printed


async def test_a_server_error_is_a_server_error(client: TestClient) -> None:
    failed = await client.get("/boom")

    failed.assert_server_error()
    #: An empty body has nothing to add to the message.
    with pytest.raises(AssertionError, match=r"Expected status 200; got 500\.$"):
        failed.assert_status(200)


async def test_a_cookie_the_route_set(client: TestClient) -> None:
    response = await client.get("/crumbs")

    response.assert_cookie("crumb", "chip")
    with pytest.raises(AssertionError, match=r"Cookie \[crumb\] is \[chip\], not \[shortbread\]"):
        response.assert_cookie("crumb", "shortbread")
    with pytest.raises(AssertionError, match=r"Cookie \[crumb\] was set, to \[chip\]"):
        response.assert_cookie_missing("crumb")


async def test_a_download_under_another_name(client: TestClient) -> None:
    download = await client.get("/download")

    with pytest.raises(AssertionError, match=r"Expected the download \[invoice.pdf\]"):
        download.assert_download("invoice.pdf")


async def test_see_in_order_and_cookies(client: TestClient) -> None:
    response = await client.get("/hello")
    response.assert_see_in_order(["Hello", "Almasix"], escape=False)
    response.assert_dont_see_text("Goodbye")

    seen = await client.get("/remember")
    seen.assert_cookie("almasix_session")
    seen.assert_cookie_missing("nothing_here")
    assert seen.cookie("almasix_session")
    assert "almasix_session" in seen.cookies


# --- what a failing assertion says ----------------------------------------------------


async def test_a_failed_status_says_what_the_body_was(client: TestClient) -> None:
    response = await client.get("/teapot")

    with pytest.raises(AssertionError, match="Expected status 200; got 418"):
        response.assert_status(200)
    with pytest.raises(AssertionError, match="short and stout"):
        response.assert_successful()
    with pytest.raises(AssertionError, match="Expected a server error"):
        response.assert_server_error()
    with pytest.raises(AssertionError, match="Expected a redirect"):
        response.assert_redirect()


async def test_every_shortcut_status_has_a_message(client: TestClient) -> None:
    response = await client.get("/echo")
    for check in (
        response.assert_created,
        response.assert_accepted,
        response.assert_bad_request,
        response.assert_unauthorized,
        response.assert_payment_required,
        response.assert_forbidden,
        response.assert_not_found,
        response.assert_method_not_allowed,
        response.assert_not_acceptable,
        response.assert_conflict,
        response.assert_gone,
        response.assert_unprocessable,
        response.assert_too_many_requests,
    ):
        with pytest.raises(AssertionError, match="Expected status"):
            check()


async def test_a_failing_body_assertion_names_the_needle(client: TestClient) -> None:
    response = await client.get("/hello")

    with pytest.raises(AssertionError, match=r"\[Goodbye\] is not in the response"):
        response.assert_see("Goodbye")
    with pytest.raises(AssertionError, match="is in the response, and should not be"):
        response.assert_dont_see("Hello")
    with pytest.raises(AssertionError, match="is not in the response text"):
        response.assert_see_text("Goodbye")
    with pytest.raises(AssertionError, match="is in the response text"):
        response.assert_dont_see_text("Hello")
    with pytest.raises(AssertionError, match="in that order"):
        response.assert_see_in_order(["Almasix", "Hello"], escape=False)
    with pytest.raises(AssertionError, match="Expected the body"):
        response.assert_content("something else")


async def test_a_failing_header_or_cookie_says_what_was_sent(client: TestClient) -> None:
    response = await client.get("/teapot")

    with pytest.raises(AssertionError, match=r"Header \[X-Absent\] is missing"):
        response.assert_header("X-Absent")
    with pytest.raises(AssertionError, match=r"Header \[X-Pot\] is \[tea\], not \[coffee\]"):
        response.assert_header("X-Pot", "coffee")
    with pytest.raises(AssertionError, match=r"Header \[X-Pot\] is present"):
        response.assert_header_missing("X-Pot")
    with pytest.raises(AssertionError, match=r"Cookie \[none\] was not set"):
        response.assert_cookie("none")
    with pytest.raises(AssertionError, match="Expected a content type"):
        response.assert_content_type("application/json")
    with pytest.raises(AssertionError, match="Expected a download"):
        response.assert_download()


async def test_a_failing_json_assertion_shows_the_payload(client: TestClient) -> None:
    response = await client.get_json("/payload")

    with pytest.raises(AssertionError, match="The JSON is missing"):
        response.assert_json({"ok": False})
    with pytest.raises(AssertionError, match="Expected the JSON"):
        response.assert_exact_json({"ok": True})
    with pytest.raises(AssertionError, match=r"has no path \[user.age\]"):
        response.assert_json_path("user.age")
    with pytest.raises(AssertionError, match="not 'Grace'"):
        response.assert_json_path("user.name", "Grace")
    with pytest.raises(AssertionError, match="which was refused"):
        response.assert_json_path("user.id", lambda value: value > 100)
    with pytest.raises(AssertionError, match=r"has the path \[user.name\]"):
        response.assert_json_missing_path("user.name")
    with pytest.raises(AssertionError, match="is not in the JSON"):
        response.assert_json_fragment({"title": "Nothing"})
    with pytest.raises(AssertionError, match="is in the JSON, and should not be"):
        response.assert_json_missing({"title": "Search"})
    with pytest.raises(AssertionError, match="Expected 9 items"):
        response.assert_json_count(9, "posts")
    with pytest.raises(AssertionError, match="nothing countable"):
        response.assert_json_count(1, "user.name")
    with pytest.raises(AssertionError, match="Expected a JSON array"):
        response.assert_json_is_array()
    with pytest.raises(AssertionError, match="Expected a JSON object"):
        response.assert_json_is_object("posts")


async def test_a_failing_structure_names_the_key_and_where(client: TestClient) -> None:
    response = await client.get_json("/payload")

    with pytest.raises(AssertionError, match=r"missing \[age\] at \[user\]"):
        response.assert_json_structure({"user": ["age"]})
    with pytest.raises(AssertionError, match=r"missing \[slug\] at \[posts.0\]"):
        response.assert_json_structure({"posts": {"*": ["slug"]}})
    with pytest.raises(AssertionError, match="Expected a list"):
        response.assert_json_structure({"user": {"*": ["id"]}})
    with pytest.raises(AssertionError, match=r"missing \[nope\] at \[the root\]"):
        response.assert_json_structure("nope")
    with pytest.raises(AssertionError, match=r"missing \[account\] at \[the root\]"):
        response.assert_json_structure({"account": ["id"]})
    response.assert_json_structure("ok")


async def test_a_body_that_is_not_json_says_so(client: TestClient) -> None:
    response = await client.get("/hello")

    with pytest.raises(AssertionError, match="not JSON"):
        response.json()


async def test_failing_validation_and_session_assertions(client: TestClient) -> None:
    response = await client.get_json("/invalid")

    with pytest.raises(AssertionError, match="Expected no validation errors"):
        response.assert_valid()
    with pytest.raises(AssertionError, match=r"Expected no errors for \['email'\]"):
        response.assert_valid("email")
    with pytest.raises(AssertionError, match=r"Expected errors for \['name'\]"):
        response.assert_invalid("name")
    with pytest.raises(AssertionError, match=r"Expected \[email\] to fail with \[Missing\]"):
        response.assert_invalid({"email": "Missing"})

    good = await client.get_json("/payload")
    with pytest.raises(AssertionError, match="the response has none"):
        good.assert_invalid()
    with pytest.raises(AssertionError, match=r"The session has no \[nothing\]"):
        good.assert_session_has("nothing")


async def test_failing_session_and_view_assertions(client: TestClient) -> None:
    stored = await client.get("/remember")

    with pytest.raises(AssertionError, match=r"session's \[seen\] is 'yes', not 'no'"):
        stored.assert_session_has("seen", "no")
    with pytest.raises(AssertionError, match="which was refused"):
        stored.assert_session_has("seen", lambda value: value == "no")
    with pytest.raises(AssertionError, match=r"session has \[seen\], and should not"):
        stored.assert_session_missing("seen")

    rendered = await client.get("/hello")
    with pytest.raises(AssertionError, match=r"view \[goodbye\] was not rendered"):
        rendered.assert_view_is("goodbye")
    with pytest.raises(AssertionError, match=r"No rendered view was given \[email\]"):
        rendered.assert_view_has("email")
    with pytest.raises(AssertionError, match=r"view's \[name\] is 'world', not 'Ada'"):
        rendered.assert_view_has("name", "Ada")
    with pytest.raises(AssertionError, match=r"was given \[name\]"):
        rendered.assert_view_missing("name")


async def test_the_no_content_check_reads_the_body(client: TestClient) -> None:
    response = await client.get("/teapot")

    with pytest.raises(AssertionError, match="Expected status 204"):
        response.assert_no_content()

    stubborn = TestResponse(response.raw)
    stubborn.raw.status_code = 204
    with pytest.raises(AssertionError, match="Expected no content"):
        stubborn.assert_no_content()
    response.raw.status_code = 418


async def test_a_redirect_to_the_wrong_place_says_where_it_went(client: TestClient) -> None:
    response = await client.get("/go-away")

    with pytest.raises(AssertionError, match=r"Expected a location of \[/elsewhere\]"):
        response.assert_location("/elsewhere")
    with pytest.raises(AssertionError, match="does not contain"):
        response.assert_redirect_contains("elsewhere")


# --- middleware ----------------------------------------------------------------------


async def test_middleware_can_be_stood_down(app: Application, client: TestClient) -> None:
    stamped = await client.get("/stamped")
    stamped.assert_header("X-Stamped", "yes")

    from almasix.testing import with_middleware, without_middleware

    without_middleware(app, "stamp")
    (await client.get("/stamped")).assert_header_missing("X-Stamped")

    with_middleware(app)
    (await client.get("/stamped")).assert_header("X-Stamped")

    without_middleware(app, ["app.http.stamp.Stamp"])
    (await client.get("/stamped")).assert_header_missing("X-Stamped")

    with_middleware(app)
    without_middleware(app)
    (await client.get("/stamped")).assert_header_missing("X-Stamped")


async def test_a_skip_list_that_names_nothing_resolvable_is_ignored(
    app: Application,
    client: TestClient,
) -> None:
    from almasix.testing import without_middleware

    without_middleware(app, "app.nowhere.Missing")

    (await client.get("/stamped")).assert_header("X-Stamped", "yes")


async def test_middleware_named_with_a_parameter_is_skipped_by_its_alias(
    app: Application,
    client: TestClient,
) -> None:
    (await client.get("/stamped-loud")).assert_header("X-Stamped", "loud")

    from almasix.testing import without_middleware

    without_middleware(app, "stamp")

    (await client.get("/stamped-loud")).assert_header_missing("X-Stamped")


async def test_middleware_that_will_not_import_is_not_quietly_skipped(
    app: Application,
    client: TestClient,
) -> None:
    """A misconfigured alias is an error, not something a skip list swallows."""
    from almasix.testing import without_middleware

    without_middleware(app, "stamp")

    with pytest.raises(ModuleNotFoundError):
        await client.get("/ghost")


def test_an_application_without_an_http_kernel_says_so() -> None:
    from almasix.testing import without_middleware

    with pytest.raises(RuntimeError, match="no HTTP kernel"):
        without_middleware(object())


# --- the test case ---------------------------------------------------------------------


class ToolkitCase:
    """The `TestCase` surface, driven by hand rather than collected by pytest."""


async def test_the_test_case_boots_and_lends_a_client(app_root: Path) -> None:
    from almasix.testing import TestCase

    class Case(TestCase):
        base_path = app_root

    case = Case()
    await case.setup()
    try:
        (await case.get("/hello")).assert_ok()
        (await case.post("/echo", {"a": "1"})).assert_json({"input": {"a": "1"}})
        (await case.put("/echo")).assert_ok()
        (await case.patch("/echo")).assert_ok()
        (await case.delete("/echo")).assert_ok()
        (await case.get_json("/payload")).assert_json_path("user.name", "Ada")
        (await case.post_json("/echo", {"a": 1})).assert_ok()
        (await case.put_json("/echo", {"a": 1})).assert_ok()
        (await case.patch_json("/echo", {"a": 1})).assert_ok()
        (await case.delete_json("/echo")).assert_ok()
        assert repr(case).startswith("Case(")
    finally:
        await case.teardown()


async def test_the_test_case_shapes_requests_the_way_the_client_does(app_root: Path) -> None:
    from almasix.testing import TestCase

    class Case(TestCase):
        base_path = app_root

    case = Case()
    await case.setup()
    try:
        case.with_headers({"X-Sent": "case"}).with_token("t").following_redirects(False)
        case.from_("/back").with_session({"seeded": 1})
        assert (await case.get("/echo")).json("sent") == "case"

        case.acting_as({"id": 3, "email": "ada@example.com"})
        (await case.get("/who")).assert_json_path("login.id", 3)
        case.assert_authenticated().assert_authenticated_as({"id": 3})
        #: The expected user may be spelled as a model, a dict, or the key itself.
        case.assert_authenticated_as(3)
        case.assert_authenticated_as(_Signed(3))
        with pytest.raises(AssertionError, match="A user is authenticated"):
            case.assert_guest()
        with pytest.raises(AssertionError, match="authenticated user is"):
            case.assert_authenticated_as({"id": 9})

        case.without_middleware()
        assert case.fake("queue")["queue"].__class__.__name__ == "FakeQueue"
    finally:
        await case.teardown()
        restore_fakes()


async def test_the_test_case_refuses_to_work_before_it_is_booted() -> None:
    from almasix.testing import TestCase

    case = TestCase()
    with pytest.raises(RuntimeError, match="not booted"):
        await case.get("/")


class _Signed:
    """Stands in for the model a guard would have signed in."""

    def __init__(self, key: int) -> None:
        self.key = key

    def get_auth_identifier(self) -> int:
        return self.key


class Gadget(SoftDeletes, Model):
    table = "gadgets"
    timestamps = False
    fillable = ("name",)


class TestCaseAsPytestCollectsIt(TestCaseBase):
    """What an application's own suite looks like: a class pytest collects.

    The lifecycle fixture boots the application, migrates a fresh database and
    wraps the test in a transaction, so each method starts from empty tables.
    """

    use_refresh_database = True
    use_database_transactions = True

    @pytest.fixture
    def almasix_base_path(self, app_root: Path) -> Path:
        return app_root

    async def test_the_application_is_up_and_the_database_is_fresh(self) -> None:
        (await self.get("/hello")).assert_ok()
        await self.assert_database_count("gadgets", 0)

        gadget = await Gadget.create({"name": "spanner"})
        await self.assert_database_has("gadgets", {"name": "spanner"})
        await self.assert_database_missing("gadgets", {"name": "hammer"})
        await self.assert_model_exists(gadget)
        await self.assert_not_soft_deleted(gadget)

        await gadget.delete()
        await self.assert_soft_deleted(gadget)

        await gadget.force_delete()
        await self.assert_model_missing(gadget)

    async def test_the_transaction_took_the_last_test_back(self) -> None:
        await self.assert_database_count("gadgets", 0)
        self.smith("list").assert_successful()


class TestCaseThatTakesTheDirectoryItIsRunIn(TestCaseBase):
    """No `base_path` and no fixture: the application is the directory it runs in."""

    async def test_it_finds_the_application_where_it_stands(self) -> None:
        assert self.base_path is None
        assert self.app.base_path == Path.cwd()
        assert self.client is not None


def test_the_application_under_test_is_the_one_bootstrap_app_builds(app_root: Path) -> None:
    """Laravel's tests require `bootstrap/app.php`; Almasix runs `bootstrap/app.py`."""
    from almasix.testing import boot_application

    entry = app_root / "bootstrap" / "app.py"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(
        "from pathlib import Path\n"
        "\n"
        "from almasix.framework import Application\n"
        "\n"
        "BASE_PATH = Path(__file__).resolve().parent.parent\n"
        "application = Application.configure(BASE_PATH).create()\n"
        "application.config.set('app.name', 'From bootstrap')\n",
        encoding="utf-8",
    )

    app = boot_application(app_root)

    assert app.config.get("app.name") == "From bootstrap"


def test_a_bootstrap_that_builds_no_application_says_so(tmp_path: Path) -> None:
    from almasix.testing import boot_application

    entry = tmp_path / "bootstrap" / "app.py"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text("asgi = None\n", encoding="utf-8")

    try:
        with pytest.raises(RuntimeError, match="defines no `application`"):
            boot_application(tmp_path)
    finally:
        #: The loader puts the application root on the import path; take it back.
        sys.path.remove(str(tmp_path))


async def test_a_guest_is_a_guest(app_root: Path) -> None:
    from almasix.testing import TestCase

    class Case(TestCase):
        base_path = app_root

    case = Case()
    await case.setup()
    try:
        await case.get("/who")
        case.assert_guest()
        with pytest.raises(AssertionError, match="No user is authenticated"):
            case.assert_authenticated()
        with pytest.raises(AssertionError, match="No user is authenticated"):
            case.assert_authenticated_as({"id": 1})
    finally:
        await case.teardown()


# --- the console -------------------------------------------------------------------------


class QuietCommand:
    """Namespace for the commands the console tests run."""


@pytest.fixture
def kernel(app_root: Path) -> Any:
    from almasix.console.command import Command
    from almasix.console.kernel import ConsoleKernel

    class GreetCommand(Command):
        signature = "demo:greet {who? : Who to greet} {--shout : Louder}"
        description = "Ask for a name and greet it"
        boots_application = False

        def handle(self) -> int:
            name = self.ask("What is your name?", self.argument("who") or "nobody")
            if self.confirm("Shout it?"):
                name = str(name).upper()
            colour = self.choice("Which colour?", ["red", "green"], "red")
            nickname = self.anticipate("A nickname?", ["Ada"], "none")
            secret = self.secret("A password?")
            self.line(f"hello {name} in {colour} ({nickname}, {len(secret)} chars)")
            self.table(["name", "colour"], [[name, colour]])
            return self.SUCCESS

    class FailCommand(Command):
        signature = "demo:fail"
        description = "Always fails"
        boots_application = False

        def handle(self) -> int:
            self.error("no")
            return self.FAILURE

    kernel = ConsoleKernel(Application(app_root))
    kernel.register(GreetCommand)
    kernel.register(FailCommand)
    return kernel


def test_a_command_answers_the_questions_a_test_gives_it(kernel: Any) -> None:
    pending = (
        smith("demo:greet", kernel=kernel)
        .expects_question("What is your name?", "Ada")
        .expects_confirmation("Shout it?", "yes")
        .expects_choice("Which colour?", "green", ["red", "green"])
        .expects_question("A nickname?", "Countess")
        .expects_question("A password?", "hunter2")
        .expects_output("hello ADA in green (Countess, 7 chars)")
        .expects_table(["name", "colour"], [["ADA", "green"]])
        .assert_successful()
    )

    pending.assert_exit_code(0).assert_ok().assert_not_exit_code(1)
    pending.assert_output_contains("hello ADA")
    pending.assert_asked("What is your name?")
    assert "exited 0" in repr(pending)


def test_a_question_with_no_answer_takes_its_default(kernel: Any) -> None:
    smith("demo:greet", kernel=kernel).expects_output("hello nobody in red").assert_successful()


def test_a_confirmation_can_be_refused(kernel: Any) -> None:
    (
        smith("demo:greet", kernel=kernel)
        .expects_question("What is your name?", "Ada")
        .expects_confirmation("Shout it?", False)
        .expects_output("hello Ada")
        .assert_successful()
    )


def test_a_failing_command_is_a_failure(kernel: Any) -> None:
    pending = smith("demo:fail", kernel=kernel).assert_failed()

    pending.assert_exit_code(1)
    with pytest.raises(AssertionError, match=r"\[demo:fail\] exited 1, not 0"):
        smith("demo:fail", kernel=kernel).assert_successful()
    with pytest.raises(AssertionError, match="succeeded, and should not have"):
        smith("demo:greet", kernel=kernel).assert_failed()
    with pytest.raises(AssertionError, match=r"exited 1, and should not have"):
        smith("demo:fail", kernel=kernel).assert_not_exit_code(1)


def test_an_expectation_the_command_does_not_meet_says_what_it_printed(kernel: Any) -> None:
    with pytest.raises(AssertionError, match=r"never printed \[goodbye\]"):
        smith("demo:greet", kernel=kernel).expects_output("goodbye").run()
    with pytest.raises(AssertionError, match=r"printed \[hello\], and should not have"):
        (
            smith("demo:greet", kernel=kernel)
            .doesnt_expect_output("farewell")
            .doesnt_expect_output("hello")
            .run()
        )
    with pytest.raises(AssertionError, match=r"printed no column \[age\]"):
        smith("demo:greet", kernel=kernel).expects_table(["age"], []).run()
    with pytest.raises(AssertionError, match=r"printed no cell \[99\]"):
        smith("demo:greet", kernel=kernel).expects_table(["name"], [[99]]).run()
    with pytest.raises(AssertionError, match=r"never printed \[goodbye\]"):
        smith("demo:greet", kernel=kernel).assert_output_contains("goodbye")
    with pytest.raises(AssertionError, match=r"never asked \[Your age\?\]"):
        smith("demo:greet", kernel=kernel).assert_asked("Your age?")
    with pytest.raises(AssertionError, match="asked: What is your name"):
        smith("demo:greet", kernel=kernel).assert_nothing_asked()


def test_a_command_that_asks_nothing_asked_nothing(kernel: Any) -> None:
    smith("demo:fail", kernel=kernel).assert_nothing_asked()


def test_a_command_runs_once_however_many_assertions_follow(kernel: Any) -> None:
    pending = smith("demo:greet", kernel=kernel).expects_question("name", "Ada")
    pending.run()
    first = pending.output
    pending.run()

    assert pending.output == first
    assert repr(PendingCommand("demo:greet")).endswith("'demo:greet', not run)")


def test_arguments_and_options_are_spelled_the_way_laravel_spells_them(kernel: Any) -> None:
    pending = smith("demo:greet", {"who": "Grace", "--shout": True}, kernel=kernel)
    pending.expects_output("hello Grace").run()

    assert pending.exit_code == 0


def test_an_answer_is_matched_to_its_question_whatever_the_order(kernel: Any) -> None:
    (
        smith("demo:greet", kernel=kernel)
        .expects_question("Which planet?", "Earth")
        .expects_question("What is your name?", "Ada")
        .expects_output("hello Ada")
        .assert_successful()
    )


def test_the_console_helper_finds_the_kernel_itself(app_root: Path) -> None:
    from almasix.console.facade import Smith

    Smith.set_kernel(None)
    try:
        smith("list").assert_successful()
    finally:
        Smith.set_kernel(None)


# --- the database ----------------------------------------------------------------------


class Widget(SoftDeletes, Model):
    table = "widgets"
    timestamps = False
    fillable = ("name",)


@pytest.fixture
async def database() -> AsyncIterator[DatabaseManager]:
    manager = DatabaseManager(
        {
            "default": "sqlite",
            "connections": {"sqlite": {"driver": "sqlite", "database": ":memory:"}},
        }
    )
    set_manager(manager)
    await Schema.create(
        "widgets",
        lambda table: (table.id(), table.string("name"), table.timestamp("deleted_at").nullable()),
    )
    yield manager
    await manager.disconnect()
    set_manager(None)


async def test_the_database_assertions(database: DatabaseManager) -> None:
    del database
    widget = await Widget.create({"name": "cog"})

    await assert_database_has("widgets", {"name": "cog"})
    await assert_database_has(Widget, {"name": "cog"})
    await assert_database_missing("widgets", {"name": "sprocket"})
    await assert_database_count("widgets", 1)
    await assert_model_exists(widget)
    await assert_not_soft_deleted(widget)

    await widget.delete()
    await assert_soft_deleted(widget)
    await assert_soft_deleted(widget, {"name": "cog"})

    await widget.force_delete()
    await assert_model_missing(widget)
    from almasix.testing import assert_database_empty

    await assert_database_empty("widgets")


async def test_a_failing_database_assertion_shows_the_table(database: DatabaseManager) -> None:
    del database
    with pytest.raises(AssertionError, match="The table holds: nothing"):
        await assert_database_has("widgets", {"name": "cog"})

    widget = await Widget.create({"name": "cog"})

    with pytest.raises(AssertionError, match="No row in .widgets. matches"):
        await assert_database_has("widgets", {"name": "sprocket"})
    with pytest.raises(AssertionError, match=r"1 row\(s\) in \[widgets\] match"):
        await assert_database_missing("widgets", {"name": "cog"})
    with pytest.raises(AssertionError, match=r"Expected 5 row\(s\)"):
        await assert_database_count("widgets", 5)
    with pytest.raises(AssertionError, match="is not soft deleted"):
        await assert_soft_deleted(widget)

    await widget.delete()
    with pytest.raises(AssertionError, match="is soft deleted"):
        await assert_not_soft_deleted(widget)

    await widget.force_delete()
    with pytest.raises(AssertionError, match="is not in .widgets."):
        await assert_model_exists(widget)
    with pytest.raises(AssertionError, match="No row in .widgets. matches"):
        await assert_soft_deleted(widget)
    with pytest.raises(AssertionError, match="No row in .widgets. matches"):
        await assert_not_soft_deleted(widget)

    remade = await Widget.create({"name": "cog"})
    with pytest.raises(AssertionError, match="is still in .widgets."):
        await assert_model_missing(remade)


async def test_a_transaction_takes_the_writes_back_with_it(database: DatabaseManager) -> None:
    del database
    async with database_transactions():
        await Widget.create({"name": "temporary"})
        await assert_database_count("widgets", 1)

    await assert_database_count("widgets", 0)


async def test_a_refreshed_database_runs_the_migrations_again(
    tmp_path: Path,
    database: DatabaseManager,
) -> None:
    del database
    migrations = tmp_path / "database" / "migrations"
    migrations.mkdir(parents=True)
    (migrations / "2026_01_01_000000_create_gears_table.py").write_text(
        "from almasix.orm import Migration, Schema\n"
        "\n"
        "\n"
        "class CreateGearsTable(Migration):\n"
        "    async def up(self) -> None:\n"
        "        await Schema.create('gears', lambda t: (t.id(), t.string('name')))\n"
        "\n"
        "    async def down(self) -> None:\n"
        "        await Schema.drop_if_exists('gears')\n",
        encoding="utf-8",
    )

    from almasix.testing import refresh_database

    await refresh_database(path=migrations)
    await assert_database_count("gears", 0)


# --- the fakes -----------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _restore_every_fake() -> Iterator[None]:
    yield
    restore_fakes()


async def test_the_queue_fake_records_instead_of_pushing() -> None:
    from almasix.queue import Job, ShouldQueue

    class SendDigest(ShouldQueue, Job):
        queue = "digests"

        async def handle(self) -> None:  # pragma: no cover - the fake never runs it
            raise AssertionError("a faked job must not run")

    class Unrelated(Job):
        async def handle(self) -> None:
            return None

    queue = fake_queue()
    from almasix.queue.helpers import dispatch, dispatch_sync

    await dispatch(SendDigest())
    await dispatch_sync(Unrelated())

    queue.assert_pushed(SendDigest)
    queue.assert_pushed("SendDigest")
    queue.assert_pushed(SendDigest, lambda job: job.queue == "digests")
    queue.assert_pushed_on("digests", SendDigest)
    queue.assert_pushed_times(SendDigest, 1)
    queue.assert_not_pushed("Nothing")
    queue.assert_count(2)
    assert len(queue.recorded()) == 2
    assert queue.recorded(SendDigest)[0].queued is True
    assert "FakeQueue(2 pushed)" == repr(queue)

    queue.flush()
    queue.assert_nothing_pushed()


async def test_the_queue_fake_can_be_told_which_jobs_to_intercept() -> None:
    from almasix.queue import Job

    ran: list[str] = []

    class Watched(Job):
        async def handle(self) -> None:  # pragma: no cover - faked away
            ran.append("watched")

    class Ignored(Job):
        async def handle(self) -> None:
            ran.append("ignored")

    queue = fake_queue([Watched])
    from almasix.queue.helpers import dispatch, dispatch_sync

    await dispatch(Watched())
    await dispatch(Ignored())
    await dispatch_sync(Ignored())
    await dispatch_sync(Watched())

    queue.assert_pushed(Watched)
    queue.assert_not_pushed(Ignored)
    assert ran == ["ignored", "ignored"]


async def test_the_queue_fake_explains_a_failure() -> None:
    from almasix.queue import Job

    class Silent(Job):
        async def handle(self) -> None:
            return None

    queue = fake_queue()
    with pytest.raises(AssertionError, match=r"\[Silent\] was not pushed. Pushed: nothing"):
        queue.assert_pushed(Silent)

    from almasix.queue.helpers import dispatch

    await dispatch(Silent())
    with pytest.raises(AssertionError, match="but not as expected"):
        queue.assert_pushed(Silent, lambda job: False)
    with pytest.raises(AssertionError, match="and should not have been"):
        queue.assert_not_pushed(Silent)
    with pytest.raises(AssertionError, match=r"Expected \[Silent\] 3 time"):
        queue.assert_pushed_times(Silent, 3)
    with pytest.raises(AssertionError, match=r"was not pushed on \[urgent\]"):
        queue.assert_pushed_on("urgent", Silent)
    with pytest.raises(AssertionError, match="Expected no jobs"):
        queue.assert_nothing_pushed()
    with pytest.raises(AssertionError, match=r"Expected 9 job\(s\)"):
        queue.assert_count(9)


async def test_the_notification_fake_records_who_would_have_been_told() -> None:
    from almasix.notifications import Notification, notify, notify_now

    class Shipped(Notification):
        def via(self, notifiable: Any) -> list[str]:
            return ["mail"]

    class Person:
        def __init__(self, key: int) -> None:
            self.key = key

        def get_key(self) -> int:
            return self.key

    ada, grace = Person(1), Person(2)
    notifications = fake_notifications()

    await notify(ada, Shipped())
    await notify_now(grace, Shipped(), ["database"])

    notifications.assert_sent_to(ada, Shipped)
    notifications.assert_sent_to(ada, "Shipped")
    notifications.assert_sent_to(
        ada, Shipped, lambda notification: isinstance(notification, Shipped)
    )
    notifications.assert_sent_to(
        grace,
        Shipped,
        lambda notification, notifiable: notifiable.get_key() == 2,
    )
    notifications.assert_sent_on_channel(Shipped, "database")
    notifications.assert_sent_times(Shipped, 2)
    notifications.assert_count(2)
    notifications.assert_not_sent_to(Person(3), Shipped)
    #: A notifiable is matched by key, so an equal object counts as the same one.
    notifications.assert_sent_to(Person(1), Shipped)
    with pytest.raises(AssertionError, match=r"was not sent to \[Person 3\]"):
        notifications.assert_sent_to(Person(3), Shipped)
    assert len(notifications.recorded()) == 2
    assert repr(notifications) == "FakeNotifications(2 sent)"

    #: A notifiable with no key of its own is matched by equality.
    await notify({"email": "ada@example.com"}, Shipped())
    notifications.assert_sent_to({"email": "ada@example.com"}, Shipped)

    notifications.flush()
    notifications.assert_nothing_sent()


async def test_the_notification_fake_explains_a_failure() -> None:
    from almasix.notifications import Notification, notify

    class Shipped(Notification):
        def via(self, notifiable: Any) -> list[str]:
            return ["mail"]

    notifications = fake_notifications()
    with pytest.raises(AssertionError, match=r"\[Shipped\] was not sent to \[ada\]"):
        notifications.assert_sent_to("ada", Shipped)

    await notify("ada", Shipped())
    with pytest.raises(AssertionError, match="and should not have been"):
        notifications.assert_not_sent_to("ada", Shipped)
    with pytest.raises(AssertionError, match=r"Expected \[Shipped\] 4 time"):
        notifications.assert_sent_times(Shipped, 4)
    with pytest.raises(AssertionError, match=r"never went out over \[sms\]"):
        notifications.assert_sent_on_channel(Shipped, "sms")
    with pytest.raises(AssertionError, match="Expected no notifications"):
        notifications.assert_nothing_sent()
    with pytest.raises(AssertionError, match=r"Expected 7 notification\(s\)"):
        notifications.assert_count(7)


def test_the_storage_fake_keeps_files_in_memory() -> None:
    from almasix.filesystem.manager import Storage, StorageManager

    Storage.set_manager(StorageManager(config={"default": "local", "disks": {}}))
    disk = fake_disk()

    disk.put("invoices/1.pdf", b"an invoice")

    disk.assert_exists("invoices/1.pdf")
    disk.assert_has("invoices/1.pdf", "an invoice")
    disk.assert_missing("invoices/2.pdf")
    disk.assert_count("", 1)
    disk.assert_directory_empty("elsewhere")
    assert repr(disk) == "FakeDisk('local')"
    assert Storage.disk() is disk

    with pytest.raises(AssertionError, match="is missing"):
        disk.assert_exists("nothing.txt")
    with pytest.raises(AssertionError, match="and should not"):
        disk.assert_missing("invoices/1.pdf")
    with pytest.raises(AssertionError, match=r"Expected 5 file\(s\)"):
        disk.assert_count("", 5)
    with pytest.raises(AssertionError, match="is not empty"):
        disk.assert_directory_empty("")
    with pytest.raises(AssertionError, match="holds b'an invoice', not"):
        disk.assert_has("invoices/1.pdf", "something else")

    Storage.set_manager(None)


def test_one_door_to_every_fake() -> None:
    assert fakeable() == [
        "broadcast",
        "event",
        "http",
        "mail",
        "notification",
        "process",
        "queue",
        "scout",
        "storage",
    ]
    assert isinstance(fake("queue"), FakeQueue)
    assert isinstance(fake("notification"), FakeNotifications)
    assert isinstance(fake("storage"), FakeDisk)
    assert fake("mail").__class__.__name__ == "MailAssertions"
    assert fake("event").__class__.__name__ == "Dispatcher"
    assert fake("http").__class__.__name__ == "Factory"
    assert fake("process").__class__.__name__ == "Factory"
    assert fake("broadcast").__class__.__name__ == "FakeBroadcaster"
    assert fake("scout").__class__.__name__ == "FakeEngine"

    with pytest.raises(ValueError, match=r"no fake for \[telepathy\]"):
        fake("telepathy")


async def test_the_mail_fake_catches_what_would_have_been_sent() -> None:
    from almasix.mail import Mail, Mailable

    class Welcome(Mailable):
        def build(self) -> None:
            self.subject("Welcome").html("<p>Hello</p>")

    #: Faking a mailer the configuration never mentioned adds it as an array one.
    from almasix.mail import MailManager

    Mail.set_manager(MailManager(config={"default": "smtp", "mailers": {}}))
    mail = Mail.fake()
    Mail.to("ada@example.com").send(Welcome())

    mail.assert_sent(Welcome)
    mail.assert_nothing_queued()


# --- time ---------------------------------------------------------------------------------


def test_the_clock_can_be_moved_and_put_back() -> None:
    from almasix.support.helpers import now, today

    real = now()
    traveller = travel(days=2)
    try:
        assert now() - real >= timedelta(days=2) - timedelta(seconds=1)
        assert today().date() == now().date()
        assert "TimeTraveller(" in repr(traveller)
    finally:
        traveller.back()
    assert now() - real < timedelta(seconds=5)

    with travel(hours=1) as moment:
        assert now() == moment
    assert now() - real < timedelta(seconds=5)


def test_the_clock_can_be_set_to_a_moment() -> None:
    from almasix.support.helpers import now

    moment = datetime(2030, 5, 4, 3, 2, 1, tzinfo=UTC)
    travel_to(moment)
    try:
        assert now() == moment
        assert now(UTC).year == 2030
    finally:
        travel_back()

    naive = datetime(2031, 1, 1)
    travel_to(naive)
    try:
        assert now().year == 2031
    finally:
        travel_back()


def test_time_can_be_frozen_around_a_callback() -> None:
    from almasix.support.helpers import now

    seen: list[datetime] = []
    result = freeze_time(lambda moment: seen.append(moment) or "done")

    assert result == "done"
    assert seen and seen[0].tzinfo is not None

    frozen = freeze_time()
    try:
        first = now()
        assert now() == first
    finally:
        frozen.back()

    with frozen_time() as moment:
        assert now() == moment


async def test_a_frozen_clock_stamps_the_models_written_under_it(
    database: DatabaseManager,
) -> None:
    del database
    await Schema.create(
        "stamped",
        lambda table: (table.id(), table.string("name"), table.timestamps()),
    )

    class Stamped(Model):
        table = "stamped"
        fillable = ("name",)

    with frozen_time(datetime(2029, 12, 31, 23, 59, tzinfo=UTC)):
        row = await Stamped.create({"name": "new year"})

    stamped_at = str(row.get_attribute("created_at"))
    assert stamped_at.startswith("2029-12-31")


# --- the generator and the command -----------------------------------------------------------


def test_make_test_writes_a_feature_test(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from almasix.console.commands.make import MakeTestCommand
    from almasix.console.kernel import ConsoleKernel

    monkeypatch.chdir(tmp_path)
    kernel = ConsoleKernel(Application(tmp_path))
    kernel.register(MakeTestCommand)

    assert kernel.run_command("make:test", {"name": "PostTest"}) == 0
    written = (tmp_path / "tests" / "feature" / "post_test.py").read_text(encoding="utf-8")
    assert "class PostTest(TestCase):" in written
    assert "await self.get(" in written

    assert kernel.run_command("make:test", {"name": "SlugTest"}, {"unit": True}) == 0
    unit = (tmp_path / "tests" / "unit" / "slug_test.py").read_text(encoding="utf-8")
    assert "class SlugTest:" in unit
    assert "TestCase" not in unit


def test_the_test_command_runs_pytest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from almasix.console.commands.test import TestCommand
    from almasix.console.kernel import ConsoleKernel

    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    kernel = ConsoleKernel(Application(tmp_path))
    kernel.register(TestCommand)

    assert kernel.run_command("test", {}, {"quiet": True}) == 0
    assert "APP_ENV=testing" in capsys.readouterr().out


def test_the_test_command_passes_the_flags_it_is_given(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from almasix.console.commands.test import TestCommand

    monkeypatch.chdir(tmp_path)
    command = TestCommand(Application(tmp_path))
    command._options = {
        "k": "search",
        "m": "smoke",
        "coverage": True,
        "parallel": True,
        "stop": True,
        "quiet": True,
    }

    assert command._flags() == [
        "-k",
        "search",
        "-m",
        "smoke",
        "--cov=app",
        "--cov-report=term-missing",
        "-n",
        "auto",
        "-x",
        "-q",
    ]


def test_the_test_command_needs_tests_to_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from almasix.console.commands.test import TestCommand
    from almasix.console.kernel import ConsoleKernel

    monkeypatch.chdir(tmp_path)
    kernel = ConsoleKernel(Application(tmp_path))
    kernel.register(TestCommand)

    assert kernel.run_command("test", {}) == 1
    assert "no tests/ directory" in capsys.readouterr().err


def test_the_test_command_says_when_pytest_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import subprocess

    from almasix.console.commands.test import TestCommand
    from almasix.console.kernel import ConsoleKernel

    (tmp_path / "tests").mkdir()
    monkeypatch.chdir(tmp_path)

    def missing(*_args: Any, **_kwargs: Any) -> None:
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", missing)
    kernel = ConsoleKernel(Application(tmp_path))
    kernel.register(TestCommand)

    assert kernel.run_command("test", {"path": "tests"}) == 1
    assert "pytest is not installed" in capsys.readouterr().err
