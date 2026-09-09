"""M33 — routing over real HTTP: binding, spoofing, domains, signatures.

Everything here needs a booted application and a request that travels through
the kernel, because that is where the parts under test live: the kernel
resolves a `{post}` into a model, an ASGI middleware rewrites a spoofed verb
before the router sees it, and `signed` answers 403 on its own.
"""

from __future__ import annotations

import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from almasix.framework import Application
from tests.support import purge_generated_app_modules

pytestmark = pytest.mark.usefixtures("app_dir")


ROUTES = """
from almasix.http import Request, json
from almasix.routing import Route
from almasix.routing.url import route as route_url
from app.models.post import Post


def show(post: Post):
    return {"found": post.title}


def show_by_slug(post: Post):
    return {"found": post.title, "by": "slug"}


Route.get("/posts/{post}", show).name("posts.show")
Route.get("/slugs/{post:slug}", show_by_slug).name("posts.slug")
Route.get("/where/{post}", show).where("post", r"[0-9]+").name("posts.where")

Route.get("/gone/{post}", show).name("posts.gone").missing(
    lambda request: json({"gone": True}, status=410)
)

Route.match(["put", "patch", "delete"], "/spoofed", lambda request: {
    "method": request.method, "real": request.real_method
}).name("spoofed")

Route.get("/greet/{name?}", lambda name=None: {"name": name or "stranger"}).name("greet")

Route.redirect("/here", "/there").name("here")
Route.permanent_redirect("/old", "/new")
Route.view("/page", "page", {"who": "world"}).name("page")

Route.get("/private", lambda: {"secret": True}).name("private").middleware("signed")
Route.get("/private-relative", lambda: {"secret": True}).name(
    "private.relative"
).middleware("signed:relative")

Route.get("/{locale}/dashboard", lambda locale: {
    "links": route_url("localized.help")
}).name("localized.dashboard").middleware("url.defaults")
Route.get("/{locale}/help", lambda locale: {"locale": locale}).name("localized.help")

with Route.group(domain="{account}.hub.test"):
    Route.get("/who", lambda account: {"account": account}).name("tenant.who")

with Route.group(domain="admin.hub.test"):
    Route.get("/panel", lambda: {"panel": True}).name("admin.panel")

Route.get("/named", lambda request: {
    "name": request.route_named("named"),
    "is": request.route_is("na*"),
    "current": Route.current_route_name(),
}).name("named")

Route.fallback(lambda: json({"fell": "through"}, status=404))
"""


def _write(root: Path, relative: str, body: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")


@pytest.fixture()
def app_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """An application on disk whose `routes/web.py` exercises M33."""
    purge_generated_app_modules()
    database = tmp_path / "database" / "app.sqlite"
    database.parent.mkdir(parents=True, exist_ok=True)

    _write(tmp_path, ".env", "APP_NAME=RoutingApp\nAPP_DEBUG=true\n")
    for package in ("app", "app/models", "app/http", "app/http/controllers"):
        _write(tmp_path, f"{package}/__init__.py", "")

    _write(
        tmp_path,
        "app/models/post.py",
        """
        from almasix.orm import Model


        class Post(Model):
            table = "posts"
            fillable = ["title", "slug"]
        """,
    )
    _write(
        tmp_path,
        "config/app.py",
        f'''
        config = {{
            "name": "RoutingApp",
            "debug": True,
            "key": "{"k" * 32}",
            "url": "http://testserver",
            "providers": [],
        }}
        ''',
    )
    _write(
        tmp_path,
        "config/database.py",
        f'''
        config = {{
            "default": "sqlite",
            "connections": {{
                "sqlite": {{"driver": "sqlite", "database": r"{database}"}}
            }},
        }}
        ''',
    )
    _write(tmp_path, "config/http.py", "config = {'middleware': [], 'middleware_aliases': {}}")
    _write(tmp_path, "config/view.py", "config = {'paths': ['resources/views']}")
    _write(tmp_path, "resources/views/page.prism.html", "<p>Hello {{ who }}</p>\n")
    _write(tmp_path, "routes/web.py", ROUTES)

    monkeypatch.chdir(tmp_path)
    sys.path.insert(0, str(tmp_path))
    monkeypatch.delenv("APP_NAME", raising=False)
    try:
        yield tmp_path
    finally:
        purge_generated_app_modules()
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))


@pytest.fixture()
def client(app_dir: Path) -> Iterator[TestClient]:
    import asyncio

    application = Application(app_dir).bootstrap()

    async def seed() -> None:
        from app.models.post import Post

        from almasix.orm import Schema

        def table(blueprint):  # type: ignore[no-untyped-def]
            blueprint.id()
            blueprint.string("title")
            blueprint.string("slug")
            blueprint.timestamps()

        await Schema.drop_if_exists("posts")
        await Schema.create("posts", table)
        await Post.create({"title": "Routing", "slug": "routing"})

    asyncio.run(seed())
    with TestClient(application.asgi) as test_client:
        yield test_client


# --- implicit model binding -------------------------------------------------


def test_a_type_hint_turns_an_id_into_a_model(client: TestClient) -> None:
    assert client.get("/posts/1").json() == {"found": "Routing"}


def test_an_id_no_row_carries_is_a_404(client: TestClient) -> None:
    assert client.get("/posts/999").status_code == 404


def test_a_binding_field_looks_the_model_up_by_that_column(client: TestClient) -> None:
    assert client.get("/slugs/routing").json() == {"found": "Routing", "by": "slug"}


def test_missing_answers_in_place_of_the_404(client: TestClient) -> None:
    response = client.get("/gone/999")

    assert response.status_code == 410
    assert response.json() == {"gone": True}


def test_a_constraint_the_value_fails_does_not_match_the_route(client: TestClient) -> None:
    # `where("post", "[0-9]+")` means `/where/abc` is not this route at all,
    # so the fallback answers rather than the handler seeing a bad id.
    assert client.get("/where/1").json() == {"found": "Routing"}
    assert client.get("/where/abc").json() == {"fell": "through"}


# --- optional parameters ----------------------------------------------------


def test_an_optional_parameter_answers_with_or_without_it(client: TestClient) -> None:
    assert client.get("/greet").json() == {"name": "stranger"}
    assert client.get("/greet/ada").json() == {"name": "ada"}


# --- method spoofing --------------------------------------------------------


@pytest.mark.parametrize("verb", ["PUT", "PATCH", "DELETE"])
def test_a_form_field_names_the_verb_html_cannot_send(client: TestClient, verb: str) -> None:
    response = client.post("/spoofed", data={"_method": verb})

    assert response.json() == {"method": verb, "real": "POST"}


def test_a_header_spoofs_the_verb_too(client: TestClient) -> None:
    response = client.post("/spoofed", headers={"X-HTTP-Method-Override": "put"})

    assert response.json() == {"method": "PUT", "real": "POST"}


def test_only_post_may_spoof_and_only_into_a_real_verb(client: TestClient) -> None:
    # A GET carrying `_method` is left alone, and a verb nobody recognizes is
    # not honored — either would let a link perform a delete.
    assert client.get("/spoofed?_method=DELETE").json() == {"fell": "through"}
    assert client.post("/spoofed", data={"_method": "BREW"}).json() == {"fell": "through"}


# --- redirects, views, fallback ---------------------------------------------


def test_a_redirect_route_needs_no_controller(client: TestClient) -> None:
    response = client.get("/here", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/there"


def test_a_permanent_redirect_says_301(client: TestClient) -> None:
    response = client.get("/old", follow_redirects=False)

    assert response.status_code == 301
    assert response.headers["location"] == "/new"


def test_a_view_route_renders_the_template(client: TestClient) -> None:
    response = client.get("/page")

    assert "Hello world" in response.text


def test_the_fallback_answers_what_no_route_claims(client: TestClient) -> None:
    response = client.get("/nothing/here/at/all")

    assert response.status_code == 404
    assert response.json() == {"fell": "through"}


# --- signed URLs over HTTP --------------------------------------------------


def test_the_signed_middleware_lets_a_valid_link_through(client: TestClient) -> None:
    from almasix.routing.url import signed_route

    target = signed_route("private")

    assert client.get(target).json() == {"secret": True}


def test_an_edited_signed_link_is_a_403(client: TestClient) -> None:
    from almasix.routing.url import signed_route

    target = signed_route("private", tampered=1)

    assert client.get(target).status_code == 200
    assert client.get(target.replace("tampered=1", "tampered=2")).status_code == 403
    assert client.get("/private").status_code == 403


def test_an_expired_link_is_a_403(client: TestClient) -> None:
    from almasix.routing.url import temporary_signed_route

    assert client.get(temporary_signed_route("private", 5)).status_code == 200
    assert client.get(temporary_signed_route("private", -5)).status_code == 403


def test_signed_relative_ignores_the_origin(client: TestClient) -> None:
    from almasix.routing.url import signed_route

    target = signed_route("private.relative", absolute=False)

    assert client.get(target).json() == {"secret": True}


# --- URL defaults per request -----------------------------------------------


def test_a_requests_locale_reaches_the_links_it_generates(client: TestClient) -> None:
    assert client.get("/fr/dashboard").json() == {"links": "http://testserver/fr/help"}
    assert client.get("/en/dashboard").json() == {"links": "http://testserver/en/help"}


# --- domain routing ---------------------------------------------------------


def test_a_domain_parameter_reaches_the_handler(client: TestClient) -> None:
    response = client.get("/who", headers={"host": "acme.hub.test"})

    assert response.json() == {"account": "acme"}


def test_a_literal_domain_only_answers_on_that_host(client: TestClient) -> None:
    assert client.get("/panel", headers={"host": "admin.hub.test"}).json() == {"panel": True}
    assert client.get("/panel", headers={"host": "other.hub.test"}).json() == {"fell": "through"}


# --- the current route ------------------------------------------------------


def test_a_request_knows_the_route_that_matched_it(client: TestClient) -> None:
    assert client.get("/named").json() == {
        "name": True,
        "is": True,
        "current": "named",
    }
