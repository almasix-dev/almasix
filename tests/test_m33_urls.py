"""M33 — URL generation: named routes, signatures, and the current request.

`url()` and `asset()` were M3's; everything a *name* makes possible is here.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from almasix.config import ConfigRepository, set_repository
from almasix.routing import Route, Router, set_router
from almasix.routing.signing import (
    expiry_from,
    has_valid_relative_signature,
    has_valid_signature,
    sign,
    signature_parameters,
)
from almasix.routing.url import (
    MissingRouteParameter,
    RouteNotFound,
    UrlGenerator,
    action,
    asset,
    route,
    secure_asset,
    secure_url,
    signed_route,
    temporary_signed_route,
    to_action,
    to_route,
    url,
)


class PostController:
    def show(self) -> None: ...
    def index(self) -> None: ...


@pytest.fixture()
def configured() -> Any:
    """An application-shaped configuration, and a router the façade reaches."""
    repository = ConfigRepository()
    repository.set("app.url", "https://shop.test")
    repository.set("app.key", "k" * 32)
    set_repository(repository)
    router = Router()
    set_router(router)
    try:
        yield repository
    finally:
        set_repository(None)
        set_router(None)


@pytest.fixture()
def routed(configured: ConfigRepository) -> Router:
    from almasix.routing.router import get_router

    Route.get("/", lambda: None, name="home")
    Route.get("/posts/{post}", lambda: None, name="posts.show")
    Route.get("/posts", [PostController, "index"], name="posts.index")
    Route.get("/users/{user}/posts/{post}", lambda: None, name="users.posts.show")
    Route.get("/greet/{name?}", lambda: None, name="greet")
    Route.get("/{locale}/about", lambda: None, name="about")
    return get_router()


# --- route() ----------------------------------------------------------------


def test_a_name_generates_its_uri(routed: Router) -> None:
    assert route("home") == "https://shop.test/"
    assert route("posts.index") == "https://shop.test/posts"


@pytest.mark.parametrize(
    "parameters",
    [7, "7", [7], (7,), {"post": 7}],
    ids=["scalar", "string", "list", "tuple", "mapping"],
)
def test_every_shape_of_parameter_means_the_same_thing(routed: Router, parameters: Any) -> None:
    assert route("posts.show", parameters) == "https://shop.test/posts/7"


def test_parameters_may_also_be_keyword_arguments(routed: Router) -> None:
    assert route("posts.show", post=7) == "https://shop.test/posts/7"
    assert route("users.posts.show", user=1, post=2) == "https://shop.test/users/1/posts/2"


def test_a_parameter_may_be_called_the_same_as_an_argument(routed: Router) -> None:
    # `{name}` is an ordinary thing to call a parameter, and it must not
    # collide with `route()`'s own first argument. Same for the rest.
    Route.get("/greet/{name}", lambda: None).name("hello")
    Route.get("/by/{parameters}", lambda: None).name("by")

    assert route("hello", name="ada") == "https://shop.test/greet/ada"
    assert route("by", parameters="x") == "https://shop.test/by/x"
    assert signed_route("hello", name="ada").startswith("https://shop.test/greet/ada?")
    assert temporary_signed_route("hello", 5, name="ada").startswith("https://shop.test/greet/ada?")
    assert to_route("hello", name="ada").headers["location"] == "/greet/ada"


def test_a_parameter_the_uri_does_not_name_becomes_the_query_string(
    routed: Router,
) -> None:
    assert route("posts.show", post=7, page=2) == "https://shop.test/posts/7?page=2"
    assert route("posts.index", {"page": 2, "sort": "new"}) == (
        "https://shop.test/posts?page=2&sort=new"
    )


def test_absolute_false_drops_the_origin(routed: Router) -> None:
    assert route("posts.show", 7, absolute=False) == "/posts/7"


def test_an_optional_parameter_may_simply_be_left_out(routed: Router) -> None:
    assert route("greet") == "https://shop.test/greet"
    assert route("greet", "ada") == "https://shop.test/greet/ada"


def test_a_parameter_value_is_url_encoded(routed: Router) -> None:
    assert route("greet", "a b/c") == "https://shop.test/greet/a%20b%2Fc"


def test_a_model_in_a_route_call_means_its_route_key(routed: Router) -> None:
    class Post:
        def get_route_key(self) -> int:
            return 42

    class Legacy:
        def get_key(self) -> int:
            return 7

    assert route("posts.show", Post()) == "https://shop.test/posts/42"
    assert route("posts.show", Legacy()) == "https://shop.test/posts/7"


def test_a_name_no_route_carries_says_which_names_exist(routed: Router) -> None:
    with pytest.raises(RouteNotFound, match="No route is named 'nope'. Named routes: about,"):
        route("nope")


def test_a_missing_parameter_names_itself(routed: Router) -> None:
    with pytest.raises(MissingRouteParameter, match="names the parameter 'post'"):
        route("posts.show")


def test_too_many_positional_parameters_is_refused(routed: Router) -> None:
    with pytest.raises(MissingRouteParameter, match="takes 1 parameter"):
        route("posts.show", [1, 2, 3])


def test_a_scalar_for_a_route_with_no_parameters_becomes_a_query(routed: Router) -> None:
    # There is no parameter to fill, so the value has nowhere to go but the
    # query string — and silently dropping it would be worse.
    assert route("home", {"page": 2}) == "https://shop.test/?page=2"


def test_the_generator_finds_no_route_for_an_empty_registry(configured: Any) -> None:
    with pytest.raises(RouteNotFound, match="Named routes: nothing"):
        route("anything")


# --- URL::defaults ----------------------------------------------------------


def test_defaults_supply_a_parameter_every_call_would_otherwise_pass(
    routed: Router,
) -> None:
    generator = UrlGenerator(root="https://shop.test")
    try:
        generator.defaults({"locale": "en"})

        assert generator.route("about") == "https://shop.test/en/about"
        # An explicit value still wins.
        assert generator.route("about", locale="fr") == "https://shop.test/fr/about"
        assert generator.defaults() == {"locale": "en"}
        # A default fills a parameter the URI names, and nothing else — it must
        # not turn up as `?locale=en` on every other route in the application.
        assert generator.route("posts.show", 7) == "https://shop.test/posts/7"
    finally:
        generator.forget_defaults()

    assert generator.defaults() == {}


def test_a_requests_defaults_do_not_outlive_it(routed: Router) -> None:
    # Two requests are in flight at once in an ASGI process; the locale one
    # arrived with must not appear in the links generated for the other.
    import asyncio

    from almasix.routing.url import pop_defaults, push_defaults

    async def visit(locale: str) -> str:
        token = push_defaults({"locale": locale})
        try:
            await asyncio.sleep(0)
            return route("about")
        finally:
            pop_defaults(token)

    async def both() -> list[str]:
        return list(await asyncio.gather(visit("en"), visit("fr")))

    assert asyncio.run(both()) == [
        "https://shop.test/en/about",
        "https://shop.test/fr/about",
    ]
    assert UrlGenerator().defaults() == {}


def test_a_routes_own_defaults_fill_a_parameter_it_names(routed: Router) -> None:
    routed.route_named("about").defaults("locale", "de")

    assert route("about") == "https://shop.test/de/about"


# --- to_route / action ------------------------------------------------------


def test_to_route_redirects_to_a_named_route(routed: Router) -> None:
    response = to_route("posts.show", 7)

    assert response.status_code == 302
    assert response.headers["location"] == "/posts/7"
    assert to_route("home", status=301).status_code == 301


def test_action_generates_the_url_of_a_controller_action(routed: Router) -> None:
    assert action([PostController, "index"]) == "https://shop.test/posts"
    assert action("PostController@index") == "https://shop.test/posts"


def test_to_action_redirects_to_a_controller_action(routed: Router) -> None:
    response = to_action([PostController, "index"])

    assert response.headers["location"] == "/posts"


def test_an_action_no_route_answers_says_so(routed: Router) -> None:
    with pytest.raises(RouteNotFound, match="No route is registered for the action"):
        action([PostController, "destroy"])


# --- signed URLs ------------------------------------------------------------


def test_a_signed_url_survives_being_read_and_not_being_edited(routed: Router) -> None:
    target = signed_route("posts.show", 7)

    assert "signature=" in target
    assert has_valid_signature(target) is True
    assert has_valid_signature(target.replace("/7?", "/8?")) is False


def test_a_signed_url_with_no_signature_is_not_valid(routed: Router) -> None:
    assert has_valid_signature("https://shop.test/posts/7") is False


def test_a_temporary_signed_url_stops_working(routed: Router) -> None:
    target = temporary_signed_route("posts.show", 30, 7)

    assert "expires=" in target
    assert has_valid_signature(target) is True

    stale = sign("https://shop.test/posts/7", expires_at=int(time.time()) - 10)
    assert has_valid_signature(stale) is False
    # The signature itself is still the right one; only the deadline passed.
    assert has_valid_signature(stale, ignore_expiry=True) is True


def test_a_relative_signature_survives_a_change_of_origin(routed: Router) -> None:
    target = signed_route("posts.show", 7, absolute=False)

    assert has_valid_relative_signature(target) is True
    assert has_valid_relative_signature(f"https://elsewhere.test{target}") is True
    # The absolute check reads the origin, so the same link fails it once the
    # request that arrives carries one — which is the point of the two shapes.
    assert has_valid_signature(f"https://shop.test{target}") is False
    assert has_valid_signature(signed_route("posts.show", 7)) is True


def test_the_query_order_does_not_change_the_signature(routed: Router) -> None:
    target = signed_route("posts.show", post=7, a=1, b=2)
    signature = target.split("signature=")[1]
    reordered = f"https://shop.test/posts/7?b=2&a=1&signature={signature}"

    assert has_valid_signature(reordered) is True


def test_signing_replaces_a_signature_rather_than_appending_a_second() -> None:
    once = sign("https://x.test/a?b=1", expires_at=None)
    twice = sign(once, expires_at=None)

    assert twice.count("signature=") == 1
    assert has_valid_signature(twice) is True


def test_an_unreadable_expiry_is_not_a_deadline_that_passed() -> None:
    # A hand-edited `expires` is caught by the signature, not by pretending
    # the link expired — the message a user gets should be the honest one.
    target = sign("https://x.test/a", expires_at=None).replace("?", "?expires=soon&")

    assert has_valid_signature(target) is False


def test_expiry_from_takes_minutes_or_seconds() -> None:
    now = int(time.time())

    assert expiry_from(1) - now == pytest.approx(60, abs=2)
    assert expiry_from(seconds=30) - now == pytest.approx(30, abs=2)
    assert expiry_from(None) - now == pytest.approx(0, abs=2)


def test_signature_parameters_drops_the_two_that_signing_owns() -> None:
    assert signature_parameters({"a": 1, "signature": "x", "expires": 2}) == {"a": 1}
    assert signature_parameters(None) == {}


def test_the_signing_key_tolerates_the_base64_prefix(configured: Any) -> None:
    from almasix.routing.signing import app_key_bytes

    configured.set("app.key", "base64:abcdef")
    assert app_key_bytes() == b"abcdef"
    configured.set("app.key", "")
    assert app_key_bytes() == b"almasix-dev-key"


def test_signing_works_without_a_booted_application() -> None:
    from almasix.routing.signing import app_key_bytes

    set_repository(None)

    assert app_key_bytes() == b"almasix-dev-key"
    assert has_valid_signature(sign("https://x.test/a", expires_at=None)) is True


# --- the generator's other methods ------------------------------------------


def test_to_appends_extra_path_segments(configured: Any) -> None:
    generator = UrlGenerator(root="https://shop.test")

    assert generator.to("users", [1, "posts", 2]) == "https://shop.test/users/1/posts/2"
    assert generator.to("users", {"id": 1}) == "https://shop.test/users/1"
    assert generator.to("users", "1") == "https://shop.test/users/1"


def test_query_merges_onto_whatever_the_path_carries(configured: Any) -> None:
    generator = UrlGenerator(root="https://shop.test")

    assert generator.query("/posts?a=1", {"b": 2}) == "https://shop.test/posts?a=1&b=2"
    assert generator.to("/posts", query={"tag": ["a", "b"]}) == (
        "https://shop.test/posts?tag=a&tag=b"
    )
    # A `None` value is left out rather than serialized as the word None.
    assert generator.to("/posts", query={"a": None}) == "https://shop.test/posts"


def test_an_external_url_passes_through_but_still_takes_a_query(configured: Any) -> None:
    generator = UrlGenerator(root="https://shop.test")

    assert generator.to("https://other.test/x") == "https://other.test/x"
    assert generator.to("//other.test/x", query={"a": 1}) == "//other.test/x?a=1"


def test_secure_forces_https_whatever_app_url_says(configured: Any) -> None:
    configured.set("app.url", "http://shop.test")

    assert secure_url("/checkout") == "https://shop.test/checkout"
    assert secure_asset("build/app.css") == "https://shop.test/build/app.css"
    assert url("/checkout") == "http://shop.test/checkout"


def test_force_scheme_applies_to_every_absolute_url(configured: Any) -> None:
    generator = UrlGenerator(root="http://shop.test")
    generator.force_scheme("https")
    try:
        assert generator.to("/a") == "https://shop.test/a"
    finally:
        generator.force_scheme(None)

    assert generator.to("/a") == "http://shop.test/a"


def test_force_root_url_overrides_app_url(configured: Any) -> None:
    generator = UrlGenerator.from_config()
    generator.force_root_url("https://cdn.test")

    assert generator.to("/a") == "https://cdn.test/a"
    generator.force_root_url(None)
    assert generator.to("/a") == "/a"


def test_a_rootless_generator_emits_paths(configured: Any) -> None:
    assert UrlGenerator().to("/a") == "/a"
    assert UrlGenerator().secure("/a") == "/a"


def test_the_base_path_survives_every_generator_method(configured: Any) -> None:
    configured.set("app.base_path", "/eu")

    assert url("users/1") == "https://shop.test/eu/users/1"
    assert url("users/1", absolute=False) == "/eu/users/1"
    assert asset("build/app.css") == "https://shop.test/eu/build/app.css"


def test_a_named_route_honors_the_base_path(routed: Router, configured: Any) -> None:
    configured.set("app.base_path", "/eu")

    assert route("posts.show", 7) == "https://shop.test/eu/posts/7"
    assert route("posts.show", 7, absolute=False) == "/eu/posts/7"


def test_the_generator_works_without_a_booted_application() -> None:
    # A script, or a unit test: there is no APP_URL to honor, so a relative
    # URL is the right answer rather than a crash.
    set_repository(None)

    assert url("/a") == "/a"
    assert asset("build/app.css") == "/build/app.css"


def test_camel_case_spellings_exist_on_the_generator(configured: Any) -> None:
    generator = UrlGenerator(root="https://shop.test")

    assert generator.secureAsset("a.css") == "https://shop.test/a.css"
    assert generator.hasValidSignature("https://shop.test/a") is False
    assert generator.forceScheme(None) is None


# --- the current request ----------------------------------------------------


def test_current_and_full_read_the_request(configured: Any) -> None:
    from starlette.datastructures import Headers

    from almasix.http.request import Request, reset_request, set_request

    class Fake:
        url = "https://shop.test/posts?page=2"
        headers = Headers({"referer": "https://shop.test/back"})

    request = Request(Fake())  # type: ignore[arg-type]
    token = set_request(request)
    try:
        generator = UrlGenerator(root="https://shop.test")

        assert generator.full() == "https://shop.test/posts?page=2"
        assert generator.current() == "https://shop.test/posts"
        assert generator.previous() == "https://shop.test/back"
        assert generator.previous_path() == "/back"
    finally:
        reset_request(token)


def test_without_a_request_the_current_url_is_the_root(configured: Any) -> None:
    generator = UrlGenerator(root="https://shop.test")

    assert generator.full() == "https://shop.test/"
    assert generator.current() == "https://shop.test/"


def test_previous_falls_back_when_there_is_no_referer(configured: Any) -> None:
    generator = UrlGenerator(root="https://shop.test")

    assert generator.previous() == "https://shop.test/"
    assert generator.previous("/dashboard") == "https://shop.test/dashboard"
    assert generator.previous_path("/dashboard") == "/dashboard"


def test_defaults_set_during_a_request_stay_in_that_request(routed: Router) -> None:
    from almasix.routing.url import pop_defaults, push_defaults

    generator = UrlGenerator(root="https://shop.test")
    token = push_defaults({"locale": "en"})
    try:
        generator.defaults({"locale": "fr"})

        assert generator.route("about") == "https://shop.test/fr/about"
    finally:
        pop_defaults(token)

    # Nothing was written application-wide, so the next request starts clean.
    assert generator.defaults() == {}


def test_a_route_with_no_parameters_ignores_a_scalar(routed: Router) -> None:
    # There is nothing to fill and nothing sensible to do with it, so the URL
    # is the route's own — better than inventing a query key for it.
    assert route("home", 7) == "https://shop.test/"


# --- the url.defaults middleware --------------------------------------------


async def test_the_defaults_middleware_copies_the_parameters_it_is_given(
    routed: Router,
) -> None:
    from almasix.http.request import Request
    from almasix.routing.middleware import SetUrlDefaults

    class Fake:
        url = "https://shop.test/fr/dashboard"
        path_params = {"locale": "fr"}

    async def call_next(request: Request) -> str:
        return route("about")

    request = Request(Fake())  # type: ignore[arg-type]

    assert await SetUrlDefaults().handle(request, call_next) == "https://shop.test/fr/about"
    # And the overlay closed, so the next request is not French.
    assert UrlGenerator().defaults() == {}


async def test_a_route_naming_no_default_passes_straight_through(routed: Router) -> None:
    from almasix.http.request import Request
    from almasix.routing.middleware import SetUrlDefaults

    class Fake:
        url = "https://shop.test/posts"
        path_params: dict[str, str] = {}

    async def call_next(request: Request) -> str:
        return "reached"

    assert await SetUrlDefaults().handle(Request(Fake()), call_next) == "reached"  # type: ignore[arg-type]


# --- Prism templates --------------------------------------------------------


def test_the_route_directives_and_helpers_reach_templates(routed: Router, tmp_path: Any) -> None:
    from almasix.prism.engine import Engine

    (tmp_path / "links.prism.html").write_text(
        "<a href=\"@route('posts.show', 7)\">post</a>\n"
        "<a href=\"@signedRoute('posts.index')\">signed</a>\n"
        '<p>{{ route("posts.index") }}</p>\n'
        "<p>{{ secure_url('/checkout') }}</p>\n"
        "<p>{{ secure_asset('build/app.css') }}</p>\n"
        "<p>{{ action([PostController, 'index']) }}</p>\n"
        "<p>{{ current_route_name() }}|{{ route_is('posts.*') }}</p>\n",
        encoding="utf-8",
    )

    rendered = Engine(paths=[tmp_path]).render("links", {"PostController": PostController})

    assert 'href="https://shop.test/posts/7"' in rendered
    assert 'href="https://shop.test/posts?signature=' in rendered
    assert "<p>https://shop.test/posts</p>" in rendered
    assert "<p>https://shop.test/checkout</p>" in rendered
    assert "<p>https://shop.test/build/app.css</p>" in rendered
    # Outside a request there is no current route, so the name is empty and
    # `route_is` is False rather than an error in the middle of a page.
    assert "<p>|False</p>" in rendered


def test_a_view_action_string_is_not_replaced_by_the_action_helper(
    routed: Router, tmp_path: Any
) -> None:
    """Forms pass ``action="/register"``; the ``action()`` helper must not win."""
    from almasix.prism.engine import Engine

    (tmp_path / "form.prism.html").write_text(
        '<form method="post" action="{{ action }}"></form>\n',
        encoding="utf-8",
    )

    rendered = Engine(paths=[tmp_path]).render("form", {"action": "/register"})

    assert 'action="/register"' in rendered
    assert "function action" not in rendered
