"""M50 part 2 — the global helpers that wrap surfaces Avalon already ships."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.requests import Request as StarletteRequest

from avalon.framework import Application, Container
from avalon.framework.helpers import (
    app,
    current_application,
    get_application,
    resolve,
    set_application,
)
from avalon.hashing import Hash, HashManager, bcrypt, set_hash_manager
from avalon.http import Redirect, Request, back, request, response
from avalon.http.request import reset_request, set_request
from avalon.log import info, logger
from avalon.session import cookie, cookie_jar, flash_input, old, session
from avalon.session.store import Session, reset_session, set_session
from avalon.support import base_path, report, report_if, report_unless, storage_path
from avalon.validation import FormRequest, ValidationException, validator


@pytest.fixture(autouse=True)
def _no_leaked_application() -> Iterator[None]:
    """Applications are process-wide; put the global back where it was."""
    previous = current_application()
    yield
    set_application(previous)


def _request(
    path: str = "/demo",
    query: str = "name=Ada",
    method: str = "GET",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> StarletteRequest:
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "headers": headers or [],
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
    }

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    return StarletteRequest(scope, receive=receive)


# --- app() and resolve() ------------------------------------------------------


def test_app_returns_the_application_and_resolves_out_of_its_container(tmp_path: Path) -> None:
    application = Application(tmp_path)

    assert app() is application
    assert get_application() is application
    assert current_application() is application
    assert app(Application) is application
    assert app(Container) is application.container
    assert resolve(Container) is application.container


def test_app_says_so_when_nothing_is_bootstrapped() -> None:
    set_application(None)

    assert current_application() is None
    with pytest.raises(RuntimeError, match="Bootstrap the Application first"):
        app()
    with pytest.raises(RuntimeError, match="Bootstrap the Application first"):
        resolve(Container)


def test_path_helpers_follow_the_application_rather_than_the_working_directory(
    tmp_path: Path,
) -> None:
    Application(tmp_path)

    assert base_path() == str(tmp_path)
    assert storage_path("logs") == str(tmp_path / "storage" / "logs")

    set_application(None)
    assert base_path() == str(Path.cwd())


# --- request() ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_returns_the_request_being_handled() -> None:
    current = await Request.create(_request())
    token = set_request(current)
    try:
        assert request() is current
        assert request("name") == "Ada"
        assert request("missing", "fallback") == "fallback"
    finally:
        reset_request(token)


def test_request_is_none_outside_a_request() -> None:
    assert request() is None
    assert request("name") is None
    assert request("name", "fallback") == "fallback"


# --- response() ---------------------------------------------------------------


def test_response_builds_a_response_from_content() -> None:
    plain = response("Hello")
    assert plain.status_code == 200
    assert plain.body == b"Hello"

    payload = response({"name": "Ada"}, status=201)
    assert payload.status_code == 201

    empty = response(None, status=204)
    assert empty.status_code == 204


def test_response_with_no_content_hands_back_the_factory() -> None:
    factory = response()

    assert factory is response()
    assert factory.json({"ok": True}).status_code == 200
    assert factory.html("<p>hi</p>").media_type == "text/html"
    assert factory.no_content().status_code == 204
    assert factory.make("body").body == b"body"
    assert factory("body").body == b"body"
    assert factory.redirect("/dashboard").status_code == 302


def test_the_factory_renders_views(tmp_path: Path) -> None:
    from avalon.caliburn.engine import Engine
    from avalon.caliburn.helpers import set_engine
    from avalon.http import response_factory

    views = tmp_path / "views"
    views.mkdir()
    (views / "welcome.cal.html").write_text("<h1>Hello {{ name }}</h1>")
    set_engine(Engine(paths=[views], cache_enabled=False))
    try:
        rendered = response_factory().view("welcome", {"name": "Ada"}, status=201)
    finally:
        set_engine(None)

    assert rendered.status_code == 201
    assert b"Hello Ada" in rendered.body


def test_the_factory_sends_files_and_streams(tmp_path: Path) -> None:
    path = tmp_path / "invoice.pdf"
    path.write_bytes(b"%PDF-1.4")
    factory = response()

    inline = factory.file(path)
    assert "attachment" not in (inline.headers.get("content-disposition") or "")

    attachment = factory.download(path)
    assert "invoice.pdf" in attachment.headers["content-disposition"]
    assert "report.pdf" in factory.download(path, "report.pdf").headers["content-disposition"]

    streamed = factory.stream(iter([b"a", b"b"]), media_type="text/plain")
    assert streamed.media_type == "text/plain"


# --- the fluent redirect, back(), and old() -----------------------------------


@pytest.mark.asyncio
async def test_a_redirect_can_flash_input_for_the_next_request() -> None:
    current = await Request.create(_request(query="name=Ada&role=admin"))
    store = Session()
    request_token, session_token = set_request(current), set_session(store)
    try:
        redirect = response().redirect("/register")
        assert isinstance(redirect, Redirect)
        assert redirect.with_input() is redirect

        store.age_flash()
        assert old() == {"name": "Ada", "role": "admin"}
        assert old("name") == "Ada"
        assert old("missing", "fallback") == "fallback"
    finally:
        reset_request(request_token)
        reset_session(session_token)


def test_a_redirect_can_flash_values_and_an_error_bag() -> None:
    store = Session()
    token = set_session(store)
    try:
        response().redirect("/profile").with_("status", "Saved.").with_errors(
            {"email": "Taken.", "name": ["Too short.", "Too rude."]}
        ).with_({"tone": "warning"}).with_input({"email": "ada@example.com"})

        store.age_flash()
        assert store.get("status") == "Saved."
        assert store.get("tone") == "warning"
        assert store.get("errors") == {
            "email": ["Taken."],
            "name": ["Too short.", "Too rude."],
        }
        assert old("email") == "ada@example.com"
    finally:
        reset_session(token)


def test_flashing_without_a_session_says_which_middleware_is_missing() -> None:
    with pytest.raises(RuntimeError, match="StartSession"):
        response().redirect("/profile").with_("status", "Saved.")
    with pytest.raises(RuntimeError, match="StartSession"):
        response().redirect("/profile").with_input({})
    with pytest.raises(RuntimeError, match="StartSession"):
        response().redirect("/profile").with_errors({"email": "Taken."})
    with pytest.raises(RuntimeError, match="StartSession"):
        flash_input({"email": "ada@example.com"})


@pytest.mark.asyncio
async def test_back_follows_the_referer_and_falls_back_when_there_is_none() -> None:
    with_referer = await Request.create(
        _request(headers=[(b"referer", b"https://example.com/posts")])
    )
    token = set_request(with_referer)
    try:
        assert back().headers["location"] == "https://example.com/posts"
        assert response().back().status_code == 302
    finally:
        reset_request(token)

    without = await Request.create(_request())
    token = set_request(without)
    try:
        assert back("/dashboard").headers["location"] == "/dashboard"
    finally:
        reset_request(token)

    assert back("/home", status=303).status_code == 303


@pytest.mark.asyncio
async def test_with_input_outside_a_request_flashes_nothing() -> None:
    store = Session()
    token = set_session(store)
    try:
        response().redirect("/register").with_input()
        store.age_flash()
        assert old() == {}
    finally:
        reset_session(token)


def test_old_reads_nothing_outside_a_session() -> None:
    assert old() == {}
    assert old("name", "fallback") == "fallback"


def test_old_ignores_a_flash_bag_that_is_not_a_mapping() -> None:
    store = Session()
    store.put("_old_input", "not a mapping")
    token = set_session(store)
    try:
        assert old() == {}
        assert old("name", "fallback") == "fallback"
    finally:
        reset_session(token)


# --- session() ----------------------------------------------------------------


def test_session_reads_values_and_writes_mappings() -> None:
    store = Session({"cart": {"total": 12}})
    token = set_session(store)
    try:
        assert session() is store
        assert session("cart") == {"total": 12}
        assert session("missing", "fallback") == "fallback"
        assert session({"coupon": "SAVE10", "seen": True}) is None
        assert store.get("coupon") == "SAVE10"
        assert store.get("seen") is True
    finally:
        reset_session(token)


def test_session_says_which_middleware_is_missing() -> None:
    with pytest.raises(RuntimeError, match="StartSession"):
        session()


# --- cookie() -----------------------------------------------------------------


def test_cookie_builds_a_cookie_without_sending_it() -> None:
    built = cookie("flavour", "mint", 60)

    assert (built.name, built.value, built.max_age) == ("flavour", "mint", 3600)
    assert built.path == "/"
    assert built.httponly is True
    assert cookie("session_only").max_age is None


def test_cookie_with_no_name_hands_back_the_jar() -> None:
    jar = cookie()

    assert jar is cookie_jar()
    assert jar.forever("id", "abc").max_age == 60 * 60 * 24 * 365 * 10
    assert jar("direct", "x", 5).max_age == 300
    assert jar.make("secure", "x", secure=True, http_only=False, same_site="strict").secure is True


def test_the_jar_queues_cookies_onto_the_outgoing_response() -> None:
    from starlette.responses import Response as StarletteResponse

    from avalon.auth.cookies import apply_queued_cookies, begin_cookie_queue, reset_cookie_queue

    token = begin_cookie_queue()
    try:
        cookie().queue("flavour", "mint", 60)
        cookie().queue(cookie().forever("id", "abc"))
        cookie().forget("stale")

        outgoing = StarletteResponse("ok")
        apply_queued_cookies(outgoing)
    finally:
        reset_cookie_queue(token)

    header = "".join(outgoing.headers.getlist("set-cookie"))
    assert "flavour=mint" in header
    assert "id=abc" in header
    assert "stale=" in header


# --- logger() and info() ------------------------------------------------------


def test_logger_and_info_write_to_the_default_channel(
    capsys: pytest.CaptureFixture[str],
) -> None:
    logging.getLogger("avalon").setLevel(logging.DEBUG)
    info("Deploy finished")
    logger("Cache warm", {"keys": 12})

    written = capsys.readouterr().err
    assert "Deploy finished" in written
    assert "Cache warm" in written
    assert "keys=12" in written


def test_logger_with_no_message_hands_back_the_writer() -> None:
    from avalon.log import LogWriter

    assert isinstance(logger(), LogWriter)


# --- bcrypt() -----------------------------------------------------------------


def test_bcrypt_hashes_with_bcrypt_whatever_the_default_driver_is() -> None:
    manager = HashManager()
    manager.configure(driver="argon2", rounds=4)
    set_hash_manager(manager)
    try:
        hashed = bcrypt("secret", {"rounds": 4})
        assert hashed.startswith("$2b$")
        assert Hash.driver("bcrypt").check("secret", hashed) is True
    finally:
        set_hash_manager(None)


# --- csrf_field() and method_field() ------------------------------------------


def test_the_form_field_helpers_return_markup_the_view_will_not_escape() -> None:
    from avalon.caliburn import csrf_field, method_field
    from avalon.caliburn.escape import e

    store = Session({"_csrf_token": "tok<en"})
    token = set_session(store)
    try:
        field = csrf_field()
        assert field.__html__() == '<input type="hidden" name="_token" value="tok&lt;en">'
        assert e(field) == field.__html__()
    finally:
        reset_session(token)

    assert method_field("put").__html__() == '<input type="hidden" name="_method" value="PUT">'


def test_templates_can_call_the_form_helpers_and_old(tmp_path: Path) -> None:
    from avalon.caliburn.engine import Engine

    views = tmp_path / "views"
    views.mkdir()
    (views / "form.cal.html").write_text(
        '<form>{!! csrf_field() !!}{!! method_field("put") !!}'
        '<input name="name" value="{{ old("name", "") }}"></form>'
    )
    engine = Engine(paths=[views], cache_enabled=False)

    store = Session()
    store.put("_old_input", {"name": "Ada"})
    session_token = set_session(store)
    try:
        rendered = engine.render("form")
    finally:
        reset_session(session_token)

    assert 'name="_token"' in rendered
    assert 'value="PUT"' in rendered
    assert 'value="Ada"' in rendered


# --- validator() --------------------------------------------------------------


class Registration(FormRequest):
    email: str
    age: int = 18


def test_validator_validates_a_payload_outside_a_request() -> None:
    check = validator({"email": "ada@example.com", "age": 36}, Registration)

    assert check.passes() is True
    assert check.fails() is False
    assert check.errors() == {}
    assert check.validated() == {"email": "ada@example.com", "age": 36}


def test_validator_reports_failures_by_field() -> None:
    check = validator({"age": "thirty"}, Registration)

    assert check.fails() is True
    assert check.passes() is False
    assert sorted(check.errors()) == ["age", "email"]
    with pytest.raises(ValidationException):
        check.validate()


def test_validator_takes_a_pydantic_model_and_message_overrides() -> None:
    from pydantic import BaseModel

    class Payload(BaseModel):
        email: str

    assert validator({"email": "ada@example.com"}, Payload).passes() is True

    check = validator(
        {},
        Payload,
        messages={"email.required": "We need an address."},
        attributes={"email": "e-mail"},
    )
    assert check.errors() == {"email": ["We need an address."]}


def test_validator_insists_on_a_schema_it_understands() -> None:
    with pytest.raises(TypeError, match="Pydantic model or a FormRequest"):
        validator({}, dict)  # type: ignore[arg-type]


# --- policy() -----------------------------------------------------------------


def test_policy_returns_the_policy_registered_for_a_model() -> None:
    from avalon.auth.access import Gate, Policy, policy

    class Post:
        pass

    class PostPolicy(Policy):
        def view(self, user: Any, post: Any = None) -> bool:
            return True

    Gate.policy(Post, PostPolicy)
    try:
        assert isinstance(policy(Post), PostPolicy)
        assert isinstance(policy(Post()), PostPolicy)
    finally:
        Gate.get_gate().flush()


def test_policy_says_when_a_model_has_none() -> None:
    from avalon.auth.access import policy

    class Unguarded:
        pass

    with pytest.raises(LookupError, match="No policy is registered for Unguarded"):
        policy(Unguarded)


# --- report() -----------------------------------------------------------------


def test_report_routes_through_the_handler_once_an_application_exists(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    Application(tmp_path)

    with caplog.at_level(logging.ERROR, logger="avalon"):
        report(ValueError("kaboom"))
        report_if(True, ValueError("conditional"))
        report_unless(False, ValueError("inverted"))
        report_if(False, ValueError("silent"))
        report_unless(True, ValueError("also silent"))

    assert "kaboom" in caplog.text
    assert "conditional" in caplog.text
    assert "inverted" in caplog.text
    assert "silent" not in caplog.text


def test_report_falls_back_to_stderr_before_the_application_boots(
    capsys: pytest.CaptureFixture[str],
) -> None:
    set_application(None)

    report(ValueError("unbooted"))

    assert "[report] ValueError: unbooted" in capsys.readouterr().err


def test_report_uses_the_bound_handler_when_the_container_has_one(tmp_path: Path) -> None:
    from avalon.exceptions.handler import Handler

    application = Application(tmp_path)
    seen: list[BaseException] = []

    class RecordingHandler(Handler):
        def report(self, exc: BaseException) -> None:
            seen.append(exc)

    application.container.instance(Handler, RecordingHandler(application))
    boom = ValueError("recorded")

    report(boom)

    assert seen == [boom]
