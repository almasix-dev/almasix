"""M33 — the router: verbs, groups, names, constraints, and resources.

Every route here is registered against a bare `Router` rather than a booted
application, because what a definition *is* should be provable without an
HTTP server. The requests those definitions answer are in
`test_m33_binding.py`.
"""

from __future__ import annotations

from typing import Any

import pytest

from almasix.routing import Route, Router, set_router
from almasix.routing.constraints import (
    ALPHA_NUMERIC_PATTERN,
    ALPHA_PATTERN,
    NUMBER_PATTERN,
    ULID_PATTERN,
    UUID_PATTERN,
    compile_uri,
    convertor_for,
)
from almasix.routing.resource import (
    RESOURCE_ACTIONS,
    resource_verbs,
    set_resource_verbs,
)
from almasix.routing.router import (
    VERBS,
    DuplicateRouteName,
    RedirectAction,
    RouteDefinition,
    ViewAction,
    describe_action,
)


@pytest.fixture()
def router() -> Any:
    """A router that is also the active one, so the `Route` façade reaches it."""
    instance = Router()
    set_router(instance)
    try:
        yield instance
    finally:
        set_router(None)


class PhotoController:
    def index(self) -> None: ...
    def create(self) -> None: ...
    def store(self) -> None: ...
    def show(self) -> None: ...
    def edit(self) -> None: ...
    def update(self) -> None: ...
    def destroy(self) -> None: ...


class CommentController(PhotoController): ...


def uris(router: Router) -> dict[str, RouteDefinition]:
    return {route.uri: route for route in router.routes}


def by_name(router: Router) -> dict[str, RouteDefinition]:
    return router.named_routes()


# --- verbs ------------------------------------------------------------------


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
def test_every_verb_registers_the_methods_it_names(
    router: Router, verb: str, expected: tuple[str, ...]
) -> None:
    route = getattr(router, verb)("/x", lambda: None)

    assert route.methods == expected


def test_a_get_route_answers_head_and_says_so_next_to_get(router: Router) -> None:
    # Laravel lists `GET|HEAD`, and a client asking only for the headers of a
    # page that exists should not be told it does not.
    assert router.get("/x", lambda: None).methods == ("GET", "HEAD")
    assert router.match(["POST", "GET"], "/y", lambda: None).methods == ("POST", "GET", "HEAD")


def test_any_answers_every_verb(router: Router) -> None:
    assert router.any("/x", lambda: None).methods == VERBS
    assert "HEAD" in VERBS


def test_match_takes_a_list_or_a_single_verb(router: Router) -> None:
    assert router.match(["PUT", "PATCH"], "/a", lambda: None).methods == ("PUT", "PATCH")
    assert router.match("delete", "/b", lambda: None).methods == ("DELETE",)


# --- routes with no controller ----------------------------------------------


def test_redirect_and_permanent_redirect_need_no_controller(router: Router) -> None:
    temporary = router.redirect("/here", "/there")
    permanent = router.permanent_redirect("/old", "/new")

    assert isinstance(temporary.action, RedirectAction)
    assert (temporary.action.destination, temporary.action.status) == ("/there", 302)
    assert (permanent.action.destination, permanent.action.status) == ("/new", 301)
    assert temporary.methods == VERBS
    assert temporary.action_name() == "redirect -> /there (302)"


def test_view_routes_render_a_template_with_no_controller(router: Router) -> None:
    route = router.view("/about", "pages.about", {"title": "About"})

    assert isinstance(route.action, ViewAction)
    assert route.action.template == "pages.about"
    assert route.action.data == {"title": "About"}
    assert route.methods == ("GET", "HEAD")
    assert route.action_name() == "view -> pages.about"


def test_a_redirect_route_answers_with_a_redirect(router: Router) -> None:
    response = router.redirect("/here", "/there", 307).action()

    assert response.status_code == 307
    assert response.headers["location"] == "/there"


def test_the_fallback_is_last_however_early_it_is_declared(router: Router) -> None:
    router.fallback(lambda: "gone")
    router.get("/real", lambda: None)

    assert [route.uri for route in router.routes] == [
        "/real",
        "/{fallback_placeholder:path}",
    ]
    assert router.routes[-1].fallback is True


def test_a_second_fallback_replaces_the_first(router: Router) -> None:
    # An application has one catch-all or none; two would mean the second is
    # dead code that `route:list` still advertises.
    router.fallback(lambda: "first")
    router.fallback(lambda: "second", name="gone")

    assert len([route for route in router.routes if route.fallback]) == 1
    assert router.fallback_route.get_name() == "gone"


# --- names ------------------------------------------------------------------


def test_a_route_is_named_fluently_or_by_keyword(router: Router) -> None:
    fluent = router.get("/a", lambda: None).name("a.show")
    keyword = router.get("/b", lambda: None, name="b.show")

    assert fluent.get_name() == "a.show"
    assert keyword.get_name() == "b.show"
    assert set(by_name(router)) == {"a.show", "b.show"}


def test_has_answers_for_one_name_or_all_of_them(router: Router) -> None:
    router.get("/a", lambda: None, name="a")
    router.get("/b", lambda: None, name="b")

    assert router.has("a") is True
    assert router.has("a", "b") is True
    assert router.has("a", "missing") is False
    assert router.has() is False


def test_named_matches_a_pattern(router: Router) -> None:
    route = router.get("/a", lambda: None, name="posts.show")

    assert route.named("posts.show") is True
    assert route.named("posts.*") is True
    assert route.named("users.*", "posts.*") is True
    assert route.named("users.*") is False
    assert router.get("/b", lambda: None).named("*") is False


def test_two_routes_cannot_share_a_name(router: Router) -> None:
    router.get("/a", lambda: None, name="home")

    with pytest.raises(DuplicateRouteName, match="Two routes are named 'home'"):
        router.get("/b", lambda: None, name="home")


def test_a_duplicate_name_is_caught_when_it_is_added_fluently(router: Router) -> None:
    router.get("/a", lambda: None, name="home")
    later = router.get("/b", lambda: None)

    with pytest.raises(DuplicateRouteName):
        later.name("home")


# --- groups -----------------------------------------------------------------


def test_a_group_shares_prefix_middleware_and_name(router: Router) -> None:
    with router.group(prefix="/admin", middleware=["auth"], name="admin."):
        route = router.get("/users", lambda: None).name("users")

    assert route.uri == "/admin/users"
    assert route.middleware_names == ["auth"]
    assert route.get_name() == "admin.users"


def test_nested_groups_compose_every_attribute(router: Router) -> None:
    with router.group(prefix="/api", middleware=["throttle"], name="api."):
        with router.group(prefix="/v1", middleware=["auth"], name="v1."):
            inner = router.get("/users", lambda: None).name("users")
        sibling = router.get("/health", lambda: None)
    outside = router.get("/", lambda: None)

    assert (inner.uri, inner.get_name()) == ("/api/v1/users", "api.v1.users")
    assert inner.middleware_names == ["throttle", "auth"]
    # The inner frame is popped, so a sibling sees only the outer group.
    assert (sibling.uri, sibling.middleware_names) == ("/api/health", ["throttle"])
    assert (outside.uri, outside.middleware_names) == ("/", [])


def test_a_controller_group_lets_a_route_name_only_its_method(router: Router) -> None:
    with router.group(controller=PhotoController):
        route = router.get("/photos", "index")
        explicit = router.get("/other", [CommentController, "index"])

    assert route.action == [PhotoController, "index"]
    assert route.action_name() == "PhotoController@index"
    # An action that already says which controller keeps it.
    assert explicit.action == [CommentController, "index"]


def test_a_group_shares_a_domain_and_where_constraints(router: Router) -> None:
    with router.group(domain="{account}.example.com", where={"id": NUMBER_PATTERN}):
        route = router.get("/orders/{id}", lambda: None)

    assert route.get_domain() == "{account}.example.com"
    assert route.wheres == {"id": NUMBER_PATTERN}


def test_a_group_can_exempt_its_routes_from_middleware(router: Router) -> None:
    with router.group(middleware=["web", "csrf"], without_middleware=["csrf"]):
        route = router.get("/webhook", lambda: None)

    assert route.middleware_names == ["web", "csrf"]
    assert route.gather_middleware() == ["web"]


def test_without_middleware_also_matches_a_parameterized_name(router: Router) -> None:
    route = router.get("/x", lambda: None, middleware=["auth:api", "web"])
    route.without_middleware("auth")

    assert route.gather_middleware() == ["web"]


def test_scope_bindings_reaches_every_route_in_the_group(router: Router) -> None:
    with router.group(scope_bindings=True):
        route = router.get("/a/{a}/b/{b}", lambda: None)

    assert route.scoped_bindings is True
    assert router.get("/c", lambda: None).scoped_bindings is None


def test_the_route_facade_delegates_to_the_active_router(router: Router) -> None:
    Route.get("/faced", lambda: None, name="faced")
    with Route.group(prefix="/g"):
        Route.post("/inside", lambda: None)

    assert "/faced" in uris(router)
    assert "/g/inside" in uris(router)
    assert Route.has("faced") is True


# --- middleware -------------------------------------------------------------


def test_middleware_takes_names_a_list_or_both(router: Router) -> None:
    route = router.get("/x", lambda: None)
    route.middleware("auth").middleware(["throttle", "verified"]).middleware("a", ["b"])

    assert route.middleware_names == ["auth", "throttle", "verified", "a", "b"]


# --- parameter constraints --------------------------------------------------


@pytest.mark.parametrize(
    ("method", "pattern"),
    [
        ("where_number", NUMBER_PATTERN),
        ("where_alpha", ALPHA_PATTERN),
        ("where_alpha_numeric", ALPHA_NUMERIC_PATTERN),
        ("where_uuid", UUID_PATTERN),
        ("where_ulid", ULID_PATTERN),
    ],
)
def test_each_where_shorthand_writes_its_pattern(
    router: Router, method: str, pattern: str
) -> None:
    route = router.get("/x/{id}", lambda: None)
    getattr(route, method)("id")

    assert route.wheres == {"id": pattern}


def test_a_where_shorthand_constrains_several_parameters_at_once(router: Router) -> None:
    route = router.get("/x/{a}/{b}", lambda: None).where_number("a", "b")
    listed = router.get("/y/{a}/{b}", lambda: None).where_number(["a", "b"])

    assert route.wheres == listed.wheres == {"a": NUMBER_PATTERN, "b": NUMBER_PATTERN}


def test_where_takes_a_name_and_a_pattern_or_a_mapping(router: Router) -> None:
    route = router.get("/x/{a}/{b}", lambda: None)
    route.where("a", "[0-9]+").where({"b": "[a-z]+"})

    assert route.wheres == {"a": "[0-9]+", "b": "[a-z]+"}

    with pytest.raises(TypeError, match="needs a pattern"):
        route.where("c")


def test_where_in_constrains_to_a_fixed_set(router: Router) -> None:
    route = router.get("/{category}", lambda: None).where_in(
        "category", ["movie", "song", "painting"]
    )

    assert route.wheres["category"] == "movie|song|painting"
    # The values are escaped, so a dot in one is a dot and not any character.
    assert router.get("/{v}", lambda: None).where_in("v", ["1.0"]).wheres["v"] == r"1\.0"


def test_a_global_pattern_constrains_the_parameter_everywhere(router: Router) -> None:
    router.pattern("id", NUMBER_PATTERN)
    route = router.get("/posts/{id}", lambda: None)

    assert route.wheres == {"id": NUMBER_PATTERN}
    assert router.global_patterns == {"id": NUMBER_PATTERN}
    # A route's own `where` wins over the global one.
    assert router.get("/x/{id}", lambda: None, where={"id": "[a-z]+"}).wheres["id"] == "[a-z]+"


def test_patterns_registers_several_at_once(router: Router) -> None:
    router.patterns({"id": NUMBER_PATTERN, "slug": "[a-z-]+"})

    assert router.global_patterns == {"id": NUMBER_PATTERN, "slug": "[a-z-]+"}


def test_camel_case_spellings_exist_for_every_fluent_method(router: Router) -> None:
    route = router.get("/x/{id}", lambda: None)

    assert route.whereNumber("id") is route
    assert route.whereAlphaNumeric("id") is route
    assert route.withoutMiddleware("csrf") is route
    assert route.scopeBindings() is route
    assert route.withTrashed() is route


# --- compiling to Starlette paths -------------------------------------------


def test_a_constraint_compiles_to_a_registered_convertor(router: Router) -> None:
    route = router.get("/posts/{post}", lambda: None).where_number("post")

    (compiled,) = route.compiled_uris()

    assert compiled.startswith("/posts/{post:almasix_")
    # The same pattern registers one convertor however many routes use it.
    assert convertor_for(NUMBER_PATTERN) == convertor_for(NUMBER_PATTERN)


def test_an_unconstrained_uri_compiles_to_itself(router: Router) -> None:
    assert router.get("/posts/{post}", lambda: None).compiled_uris() == ("/posts/{post}",)


def test_an_optional_parameter_compiles_to_a_path_with_and_without_it() -> None:
    assert compile_uri("/user/{name?}", {}) == ("/user/{name}", "/user")
    assert compile_uri("/a/{b?}/{c?}", {}) == ("/a/{b}/{c}", "/a/{b}", "/a")


def test_starlettes_own_convertors_survive_compilation() -> None:
    # `{file:path}` is a converter, not a binding field, so it stays.
    assert compile_uri("/download/{file:path}", {}) == ("/download/{file:path}",)


def test_a_binding_field_is_read_off_the_uri_and_left_out_of_the_path() -> None:
    assert compile_uri("/users/{user:slug}", {}) == ("/users/{user}",)


def test_binding_fields_names_the_column_a_parameter_binds_by(router: Router) -> None:
    route = router.get("/users/{user:slug}/posts/{post}", lambda: None)

    assert route.binding_fields() == {"user": "slug"}
    assert route.parameter_names() == ["user", "post"]


# --- defaults, missing, trashed ---------------------------------------------


def test_defaults_supply_a_parameter_the_url_did_not_carry(router: Router) -> None:
    route = router.get("/{locale}/about", lambda: None)
    route.defaults("locale", "en").defaults({"theme": "dark"})

    assert route.default_values == {"locale": "en", "theme": "dark"}


def test_missing_holds_what_to_answer_when_binding_finds_nothing(router: Router) -> None:
    handler = lambda: "gone"
    route = router.get("/x/{y}", lambda: None).missing(handler)

    assert route.missing_handler is handler


def test_with_trashed_and_scope_bindings_are_switches(router: Router) -> None:
    route = router.get("/x/{y}", lambda: None)

    assert route.with_trashed().trashed is True
    assert route.with_trashed(False).trashed is False
    assert route.scope_bindings().scoped_bindings is True
    assert route.without_scoped_bindings().scoped_bindings is False


# --- resources --------------------------------------------------------------


def test_a_resource_registers_laravels_seven(router: Router) -> None:
    router.resource("photos", PhotoController)

    assert [
        ("|".join(route.methods), route.uri, route.get_name())
        for route in router.routes
    ] == [
        ("GET|HEAD", "/photos", "photos.index"),
        ("GET|HEAD", "/photos/create", "photos.create"),
        ("POST", "/photos", "photos.store"),
        ("GET|HEAD", "/photos/{photo}", "photos.show"),
        ("GET|HEAD", "/photos/{photo}/edit", "photos.edit"),
        ("PUT|PATCH", "/photos/{photo}", "photos.update"),
        ("DELETE", "/photos/{photo}", "photos.destroy"),
    ]
    assert [action for action, _, _ in RESOURCE_ACTIONS] == [
        "index",
        "create",
        "store",
        "show",
        "edit",
        "update",
        "destroy",
    ]


def test_an_api_resource_leaves_out_the_two_that_serve_forms(router: Router) -> None:
    router.api_resource("photos", PhotoController)

    assert [route.get_name() for route in router.routes] == [
        "photos.index",
        "photos.store",
        "photos.show",
        "photos.update",
        "photos.destroy",
    ]


def test_only_and_except_narrow_a_resource(router: Router) -> None:
    router.resource("a", PhotoController).only("index", "show")
    router.resource("b", PhotoController).except_("create", "edit", "destroy")

    assert [route.get_name() for route in router.routes if route.uri.startswith("/a")] == [
        "a.index",
        "a.show",
    ]
    assert [route.get_name() for route in router.routes if route.uri.startswith("/b")] == [
        "b.index",
        "b.store",
        "b.show",
        "b.update",
    ]


def test_only_and_except_take_a_list_too(router: Router) -> None:
    router.resource("a", PhotoController).only(["index"])

    assert [route.get_name() for route in router.routes] == ["a.index"]


def test_laravels_except_spelling_reaches_the_python_method(router: Router) -> None:
    # `except` is a keyword, so the method is `except_` — but the attribute
    # exists under Laravel's name for anyone porting code line by line.
    pending = router.resource("a", PhotoController)
    getattr(pending, "except")("create", "edit", "store", "update", "destroy")

    assert [route.get_name() for route in pending.routes] == ["a.index", "a.show"]


def test_a_dotted_name_nests_the_resource(router: Router) -> None:
    router.resource("photos.comments", CommentController)

    assert [(route.uri, route.get_name()) for route in router.routes] == [
        ("/photos/{photo}/comments", "photos.comments.index"),
        ("/photos/{photo}/comments/create", "photos.comments.create"),
        ("/photos/{photo}/comments", "photos.comments.store"),
        ("/photos/{photo}/comments/{comment}", "photos.comments.show"),
        ("/photos/{photo}/comments/{comment}/edit", "photos.comments.edit"),
        ("/photos/{photo}/comments/{comment}", "photos.comments.update"),
        ("/photos/{photo}/comments/{comment}", "photos.comments.destroy"),
    ]


def test_a_slash_in_the_name_is_a_prefix_and_does_not_nest(router: Router) -> None:
    router.api_resource("api/tags", PhotoController).only("index", "show")

    assert [(route.uri, route.get_name()) for route in router.routes] == [
        ("/api/tags", "tags.index"),
        ("/api/tags/{tag}", "tags.show"),
    ]


def test_shallow_nesting_drops_the_parent_where_the_child_id_is_enough(
    router: Router,
) -> None:
    router.resource("photos.comments", CommentController).shallow()

    assert [(route.uri, route.get_name()) for route in router.routes] == [
        ("/photos/{photo}/comments", "photos.comments.index"),
        ("/photos/{photo}/comments/create", "photos.comments.create"),
        ("/photos/{photo}/comments", "photos.comments.store"),
        ("/comments/{comment}", "comments.show"),
        ("/comments/{comment}/edit", "comments.edit"),
        ("/comments/{comment}", "comments.update"),
        ("/comments/{comment}", "comments.destroy"),
    ]


def test_shallow_on_an_unnested_resource_changes_nothing(router: Router) -> None:
    router.resource("photos", PhotoController).shallow().only("show")

    assert router.routes[0].uri == "/photos/{photo}"
    assert router.routes[0].get_name() == "photos.show"


def test_names_renames_the_routes_per_action_or_all_at_once(router: Router) -> None:
    router.resource("a", PhotoController).only("index", "show").names(
        {"index": "a.list"}
    )
    router.resource("b", PhotoController).only("index").names("shelf")

    assert [route.get_name() for route in router.routes] == ["a.list", "a.show", "shelf.index"]


def test_parameters_renames_the_uri_parameter(router: Router) -> None:
    router.resource("users", PhotoController).only("show").parameters(
        {"users": "admin_user"}
    )
    router.resource("posts", PhotoController).only("show").parameters("slug")

    assert [route.uri for route in router.routes] == [
        "/users/{admin_user}",
        "/posts/{slug}",
    ]


def test_scoped_binds_a_nested_child_through_its_parent(router: Router) -> None:
    pending = router.resource("photos.comments", CommentController).only("show").scoped(
        {"comment": "slug"}
    )
    (route,) = pending.routes

    assert route.uri == "/photos/{photo}/comments/{comment:slug}"
    assert route.scoped_bindings is True
    assert route.binding_fields() == {"comment": "slug"}


def test_scoped_with_no_columns_still_scopes(router: Router) -> None:
    (route,) = router.resource("photos.comments", CommentController).only("show").scoped().routes

    assert route.uri == "/photos/{photo}/comments/{comment}"
    assert route.scoped_bindings is True


def test_resource_middleware_applies_to_all_actions_or_some(router: Router) -> None:
    router.resource("a", PhotoController).only("index", "store").middleware("auth")
    router.resource("b", PhotoController).only("index", "store").middleware(
        {"store": ["csrf"]}
    )

    routes = by_name(router)
    assert routes["a.index"].middleware_names == ["auth"]
    assert routes["a.store"].middleware_names == ["auth"]
    assert routes["b.index"].middleware_names == []
    assert routes["b.store"].middleware_names == ["csrf"]


def test_resource_without_middleware_exempts_all_or_some(router: Router) -> None:
    router.resource("a", PhotoController).only("index", "store").middleware(
        ["web", "csrf"]
    ).without_middleware({"store": "csrf"})
    router.resource("b", PhotoController).only("index").middleware(
        ["web", "csrf"]
    ).without_middleware("csrf")

    routes = by_name(router)
    assert routes["a.index"].gather_middleware() == ["web", "csrf"]
    assert routes["a.store"].gather_middleware() == ["web"]
    assert routes["b.index"].gather_middleware() == ["web"]


def test_a_resource_carries_where_missing_and_trashed_onto_its_routes(
    router: Router,
) -> None:
    handler = lambda: "gone"
    router.resource("a", PhotoController).only("show", "update").where(
        {"a": NUMBER_PATTERN}
    ).missing(handler).with_trashed(["show"])

    routes = by_name(router)
    assert routes["a.show"].wheres == {"a": NUMBER_PATTERN}
    assert routes["a.show"].missing_handler is handler
    assert routes["a.show"].trashed is True
    assert routes["a.update"].trashed is False


def test_with_trashed_true_reaches_every_action(router: Router) -> None:
    router.resource("a", PhotoController).only("show", "update").with_trashed()

    assert all(route.trashed for route in router.routes)


def test_resource_options_may_also_be_keyword_arguments(router: Router) -> None:
    router.resource(
        "a",
        PhotoController,
        only=["index"],
        names={"index": "a.list"},
        parameters={"a": "key"},
        middleware=["auth"],
        where={"key": NUMBER_PATTERN},
    )

    (route,) = router.routes
    assert (route.get_name(), route.middleware_names) == ("a.list", ["auth"])
    assert route.wheres == {"key": NUMBER_PATTERN}


def test_resources_registers_many_at_once(router: Router) -> None:
    pending = router.resources({"photos": PhotoController, "comments": CommentController})

    assert {route.get_name() for route in router.routes} >= {
        "photos.index",
        "comments.index",
    }
    assert len(pending) == 2


def test_api_resources_registers_many_without_the_form_actions(router: Router) -> None:
    router.api_resources({"a": PhotoController, "b": CommentController})

    assert not [route for route in router.routes if "create" in route.uri]


def test_a_resource_with_no_fluent_call_registers_on_its_own(router: Router) -> None:
    # `Route.resource(...)` as a statement is the common case, and it must not
    # need a trailing call that Laravel does not have.
    router.resource("photos", PhotoController)

    assert len(router.routes) == 7


def test_a_fluent_call_rewrites_the_routes_rather_than_adding_more(
    router: Router,
) -> None:
    pending = router.resource("photos", PhotoController)
    assert len(router.routes) == 7

    pending.only("index", "show").names({"index": "photos.list"})

    assert [route.get_name() for route in router.routes] == ["photos.list", "photos.show"]
    assert pending.routes == router.routes
    assert pending.register() == router.routes
    assert list(pending) == router.routes
    assert len(pending) == 2


# --- singletons -------------------------------------------------------------


def test_a_singleton_has_no_id_and_nothing_to_list(router: Router) -> None:
    router.singleton("profile", PhotoController)

    assert [("|".join(route.methods), route.uri, route.get_name()) for route in router.routes] == [
        ("GET|HEAD", "/profile", "profile.show"),
        ("GET|HEAD", "/profile/edit", "profile.edit"),
        ("PUT|PATCH", "/profile", "profile.update"),
    ]


def test_a_creatable_singleton_gains_create_store_and_destroy(router: Router) -> None:
    router.singleton("profile", PhotoController).creatable()

    assert [route.get_name() for route in router.routes] == [
        "profile.create",
        "profile.store",
        "profile.show",
        "profile.edit",
        "profile.update",
        "profile.destroy",
    ]


def test_a_destroyable_singleton_gains_only_destroy(router: Router) -> None:
    router.singleton("profile", PhotoController).destroyable()

    assert [route.get_name() for route in router.routes] == [
        "profile.show",
        "profile.edit",
        "profile.update",
        "profile.destroy",
    ]


def test_an_api_singleton_leaves_out_edit(router: Router) -> None:
    router.api_singleton("profile", PhotoController)

    assert [route.get_name() for route in router.routes] == [
        "profile.show",
        "profile.update",
    ]


def test_singletons_registers_many_at_once(router: Router) -> None:
    router.singletons({"profile": PhotoController})
    router.api_singletons({"settings": PhotoController})

    assert {route.get_name() for route in router.routes} >= {
        "profile.show",
        "settings.show",
    }


# --- localized resource URIs ------------------------------------------------


def test_the_create_and_edit_segments_are_translatable(router: Router) -> None:
    set_resource_verbs(create="crear", edit="editar")
    try:
        router.resource("fotos", PhotoController).only("create", "edit")

        assert [route.uri for route in router.routes] == [
            "/fotos/crear",
            "/fotos/{foto}/editar",
        ]
        assert resource_verbs() == {"create": "crear", "edit": "editar"}
    finally:
        set_resource_verbs(create="create", edit="edit")


def test_set_resource_verbs_ignores_what_it_is_not_given() -> None:
    set_resource_verbs(create="crear")
    try:
        assert resource_verbs() == {"create": "crear", "edit": "edit"}
    finally:
        set_resource_verbs(create="create", edit="edit")


# --- explicit binding registration ------------------------------------------


def test_bind_and_model_are_registered_by_parameter_name(router: Router) -> None:
    resolver = lambda value: value.upper()
    missing = lambda: "gone"
    router.bind("code", resolver)
    router.model("photo", PhotoController, missing)

    assert router.binder_for("code") is resolver
    assert router.model_for("photo") == (PhotoController, missing)
    assert router.binder_for("nothing") is None
    assert router.model_for("nothing") is None


def test_the_facade_registers_patterns_and_bindings(router: Router) -> None:
    Route.pattern("id", NUMBER_PATTERN)
    Route.patterns({"slug": "[a-z-]+"})
    Route.bind("code", str.upper)
    Route.model("photo", PhotoController)

    assert router.global_patterns == {"id": NUMBER_PATTERN, "slug": "[a-z-]+"}
    assert router.binder_for("code") is str.upper
    assert router.model_for("photo") == (PhotoController, None)


# --- describing an action ---------------------------------------------------


def test_an_action_describes_itself_however_it_was_written() -> None:
    def handler() -> None: ...

    assert describe_action([PhotoController, "show"]) == "PhotoController@show"
    assert describe_action(("PhotoController", "show")) == "PhotoController@show"
    assert describe_action("app.Controller@show") == "app.Controller@show"
    assert describe_action(handler) == "test_an_action_describes_itself_however_it_was_written.<locals>.handler"
    assert describe_action(RedirectAction("/x")) == "redirect -> /x (302)"
    assert describe_action(3) == "3"


# --- websockets -------------------------------------------------------------


def test_a_websocket_route_takes_a_name_and_middleware_the_same_way(
    router: Router,
) -> None:
    with router.group(prefix="/ws", middleware=["auth"], name="ws."):
        route = router.websocket("/feed", lambda socket: None, name="feed")
    route.middleware("verified")

    assert (route.uri, route.get_name()) == ("/ws/feed", "ws.feed")
    assert route.gather_middleware() == ["auth", "verified"]
    assert route.name("!").get_name() == "ws.feed!"


def test_an_unnamed_websocket_route_has_no_name(router: Router) -> None:
    assert router.websocket("/feed", lambda socket: None).get_name() is None


# --- the router without an application --------------------------------------


def test_the_facade_says_what_is_missing_before_bootstrap() -> None:
    set_router(None)

    with pytest.raises(RuntimeError, match="Router is not set"):
        Route.get("/x", lambda: None)


def test_a_route_repr_names_what_it_is(router: Router) -> None:
    route = router.get("/x", lambda: None, name="x")

    assert repr(route) == "<Route GET|HEAD /x name='x'>"
