"""M33 — the `Route` façade, and the edges the other M33 files do not reach.

`Route` is the surface an application writes routes with, so every static on it
gets exercised here against a real router.
"""

from __future__ import annotations

from typing import Any

import pytest

from almasix.config import ConfigRepository, set_repository
from almasix.routing import Route, Router, set_router
from almasix.routing.constraints import convertor_for
from almasix.routing.resource import resource_verbs, set_resource_verbs
from almasix.routing.router import DuplicateRouteName, _flatten, _register_name


class Controller:
    def index(self) -> None: ...
    def show(self) -> None: ...
    def store(self) -> None: ...
    def update(self) -> None: ...
    def destroy(self) -> None: ...
    def create(self) -> None: ...
    def edit(self) -> None: ...


@pytest.fixture()
def router() -> Any:
    repository = ConfigRepository()
    repository.set("app.url", "https://shop.test")
    set_repository(repository)
    instance = Router()
    set_router(instance)
    try:
        yield instance
    finally:
        set_router(None)
        set_repository(None)


# --- every verb the façade offers -------------------------------------------


@pytest.mark.parametrize(
    ("verb", "expected"),
    [
        ("get", ("GET", "HEAD")),
        ("head", ("HEAD",)),
        ("post", ("POST",)),
        ("put", ("PUT",)),
        ("patch", ("PATCH",)),
        ("delete", ("DELETE",)),
        ("options", ("OPTIONS",)),
    ],
)
def test_the_facade_registers_each_verb(
    router: Router, verb: str, expected: tuple[str, ...]
) -> None:
    getattr(Route, verb)("/thing", lambda: None)

    (route,) = router.routes
    assert route.methods == expected


def test_any_answers_every_verb(router: Router) -> None:
    Route.any("/thing", lambda: None)

    assert set(router.routes[0].methods) >= {"GET", "POST", "PUT", "PATCH", "DELETE"}


def test_match_answers_the_verbs_it_is_given(router: Router) -> None:
    Route.match(["post", "put"], "/thing", lambda: None)

    assert router.routes[0].methods == ("POST", "PUT")


def test_the_facade_registers_the_controller_less_shapes(router: Router) -> None:
    Route.redirect("/a", "/b")
    Route.permanent_redirect("/c", "/d")
    Route.view("/e", "page")
    Route.fallback(lambda: None)

    assert [route.uri for route in router.routes] == [
        "/a",
        "/c",
        "/e",
        "/{fallback_placeholder:path}",
    ]


def test_the_facade_registers_a_websocket(router: Router) -> None:
    Route.websocket("/live", lambda socket: None)

    assert [route.uri for route in router.websocket_routes] == ["/live"]


# --- resources through the façade -------------------------------------------


def test_the_facade_registers_every_resource_shape(router: Router) -> None:
    Route.resource("photos", Controller)
    Route.api_resource("api/tags", Controller)
    Route.singleton("profile", Controller)
    Route.api_singleton("api/settings", Controller)

    # An API resource has no `create` or `edit`, there being no form to show.
    names = {route.get_name() for route in router.routes}
    assert "photos.create" in names
    assert "tags.create" not in names
    assert "profile.edit" in names
    assert "settings.edit" not in names
    assert [route.uri for route in router.routes if route.get_name() == "photos.create"] == [
        "/photos/create"
    ]


def test_the_facade_registers_resources_in_bulk(router: Router) -> None:
    Route.resources({"photos": Controller})
    Route.api_resources({"api/tags": Controller})
    Route.singletons({"profile": Controller})
    Route.api_singletons({"api/settings": Controller})

    # A slash in a resource name is a URI prefix, so it does not enter the
    # route name — `api/tags` is reached at `/api/tags` and named `tags.*`.
    names = {route.get_name() for route in router.routes}
    assert {"photos.index", "tags.index", "profile.show", "settings.show"} <= names
    uris = {route.uri for route in router.routes}
    assert {"/photos", "/api/tags", "/profile", "/api/settings"} <= uris


# --- the current route ------------------------------------------------------


def test_with_no_request_the_current_route_is_nothing(router: Router) -> None:
    assert Route.current() is None
    assert Route.current_route_name() is None
    assert Route.current_route_action() is None
    assert Route.is_("anything") is False


def test_the_current_route_reads_the_request(router: Router) -> None:
    from almasix.http.request import Request, reset_request, set_request

    route = Route.get("/posts", [Controller, "index"]).name("posts.index")

    class Fake:
        url = "https://shop.test/posts"
        path_params: dict[str, Any] = {}

    request = Request(Fake())  # type: ignore[arg-type]
    request.matched_route = route
    token = set_request(request)
    try:
        assert Route.current() is route
        assert Route.current_route_name() == "posts.index"
        assert Route.current_route_action() == "Controller@index"
        assert Route.is_("posts.*") is True
        assert Route.is_("users.*") is False
    finally:
        reset_request(token)


# --- names ------------------------------------------------------------------


def test_two_routes_with_one_name_is_refused(router: Router) -> None:
    Route.get("/a", lambda: None).name("same")

    with pytest.raises(DuplicateRouteName, match="Two routes are named 'same'"):
        Route.get("/b", lambda: None).name("same")


def test_has_reports_whether_every_name_is_registered(router: Router) -> None:
    Route.get("/a", lambda: None).name("a")
    Route.get("/b", lambda: None).name("b")

    assert Route.has("a", "b") is True
    assert Route.has("a", "missing") is False


def test_registering_a_name_with_no_router_does_nothing(router: Router) -> None:
    # A `RouteDefinition` built by hand, before `set_router`, has no registry
    # to collide in — and must not raise on the way past.
    route = Route.get("/a", lambda: None)
    set_router(None)

    _register_name(route)


# --- domains ----------------------------------------------------------------


def test_a_route_reports_the_domain_it_answers_on(router: Router) -> None:
    route = Route.get("/who", lambda: None).domain("{account}.hub.test")

    assert route.get_domain() == "{account}.hub.test"
    assert Route.get("/open", lambda: None).get_domain() is None


def test_a_group_domain_reaches_the_routes_inside_it(router: Router) -> None:
    with Route.group(domain="admin.hub.test"):
        route = Route.get("/panel", lambda: None)

    assert route.get_domain() == "admin.hub.test"


# --- group middleware -------------------------------------------------------


def test_a_group_middleware_list_is_readable_while_the_group_is_open(
    router: Router,
) -> None:
    with router.group(middleware=["web", "auth"]):
        assert router._group_middleware() == ["web", "auth"]

    assert router._group_middleware() == []


# --- localized resource verbs -----------------------------------------------


def test_the_create_and_edit_segments_can_be_translated(router: Router) -> None:
    original = resource_verbs()
    try:
        set_resource_verbs(create="crear", edit="editar")
        Route.resource("fotos", Controller)

        uris = {route.uri for route in router.routes}
        assert "/fotos/crear" in uris
        assert "/fotos/{foto}/editar" in uris
    finally:
        set_resource_verbs(**original)

    assert resource_verbs() == original


def test_translating_neither_verb_changes_nothing(router: Router) -> None:
    before = resource_verbs()

    set_resource_verbs()

    assert resource_verbs() == before


# --- small internals --------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("auth", ["auth"]),
        (["auth", "web"], ["auth", "web"]),
        ((name for name in ["a", "b"]), ["a", "b"]),
        (7, ["7"]),
    ],
)
def test_middleware_names_flatten_from_every_shape(given: Any, expected: list[str]) -> None:
    assert _flatten([given]) == expected


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("index", ["index"]),
        (["index", "show"], ["index", "show"]),
        (7, ["7"]),
        (None, []),
        (True, []),
    ],
)
def test_resource_action_names_flatten_from_every_shape(
    given: Any, expected: list[str]
) -> None:
    from almasix.routing.resource import _names

    assert _names([given]) == expected


def test_a_registered_convertor_round_trips_a_value() -> None:
    from starlette.convertors import CONVERTOR_TYPES

    name = convertor_for(r"[0-9]+")
    convertor = CONVERTOR_TYPES[name]

    assert convertor.convert("42") == "42"
    assert convertor.to_string(42) == "42"
    # The same pattern is the same convertor, registered once.
    assert convertor_for(r"[0-9]+") == name


def test_the_signature_helpers_are_on_the_generator_too() -> None:
    from almasix.routing.signing import sign
    from almasix.routing.url import UrlGenerator

    generator = UrlGenerator(root="https://shop.test")
    absolute = sign("https://shop.test/a")
    relative = sign("/a", absolute=False)

    assert generator.has_valid_signature(absolute) is True
    assert generator.has_valid_relative_signature(relative) is True
    assert generator.has_valid_signature("https://shop.test/a") is False


# --- resource options passed as constructor keywords ------------------------


def test_a_resource_takes_its_options_up_front(router: Router) -> None:
    # `Route.resource("photos", C, parameters="slug", names="pics")` is the
    # same statement as the fluent calls, and some applications prefer it.
    Route.resource(
        "photos",
        Controller,
        only=["show"],
        parameters="slug",
        names="pics",
    )

    (route,) = router.routes
    assert route.uri == "/photos/{slug}"
    assert route.get_name() == "pics.show"


def test_a_resource_may_be_named_per_action_up_front(router: Router) -> None:
    Route.resource("photos", Controller, only=["index"], names={"index": "gallery"})

    assert router.routes[0].get_name() == "gallery"


def test_a_parameter_map_may_be_passed_up_front(router: Router) -> None:
    Route.resource("photos", Controller, only=["show"], parameters={"photos": "photo_id"})

    assert router.routes[0].uri == "/photos/{photo_id}"
