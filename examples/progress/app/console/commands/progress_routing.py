"""Demo routing DX, named routes, and URL generation (M33)."""

from __future__ import annotations

from almasix.console.command import Command
from almasix.routing import Route, Router, set_router
from almasix.routing.binding import route_key_name
from almasix.routing.resource import resource_verbs, set_resource_verbs
from almasix.routing.signing import has_valid_relative_signature, has_valid_signature, sign
from almasix.routing.url import (
    UrlGenerator,
    action,
    route,
    signed_route,
    temporary_signed_route,
    url,
)


class PhotoController:
    """A resource controller. Only the method names matter here."""

    def index(self) -> None: ...
    def create(self) -> None: ...
    def store(self) -> None: ...
    def show(self) -> None: ...
    def edit(self) -> None: ...
    def update(self) -> None: ...
    def destroy(self) -> None: ...


class CommentController(PhotoController):
    """The child of a nested resource."""


class Article:
    """A model, so binding has something to read a route key from."""

    primary_key = "id"

    @staticmethod
    def get_route_key_name() -> str:
        return "slug"

    def __init__(self, key: str) -> None:
        self.key = key

    def get_route_key(self) -> str:
        return self.key


class ProgressRoutingCommand(Command):
    signature = "progress:routing"
    description = "Demo routing DX, named routes, resources, and URL generation (M33)"

    def handle(self) -> int:
        # Each section gets a router of its own, so the demo never describes
        # the example app's own routes and two sections cannot collide on a
        # name. `set_router` is restored at the end.
        previous = set_router(Router())
        try:
            self._verbs()
            self._constraints()
            self._groups()
            self._resources()
            self._singletons()
            self._binding()
            self._urls()
            self._signing()
            self._defaults()
            self._current()
        finally:
            set_router(previous)

        self.success("routing demo ok")
        return 0

    def _fresh(self) -> Router:
        """A router with nothing in it, installed as the active one."""
        router = Router()
        set_router(router)
        return router

    def _describe(self, *routes: object) -> None:
        for entry in routes:
            methods = "|".join(entry.methods)  # type: ignore[attr-defined]
            name = entry.get_name() or "—"  # type: ignore[attr-defined]
            self.line(f"    {methods:16} {entry.uri:34} {name}")  # type: ignore[attr-defined]

    # -- verbs and shapes ----------------------------------------------------

    def _verbs(self) -> None:
        self._fresh()
        index = Route.get("/photos", [PhotoController, "index"]).name("photos.index")
        head = Route.head("/photos", [PhotoController, "index"])
        matched = Route.match(["put", "patch"], "/photos/{photo}", [PhotoController, "update"])
        anything = Route.any("/anything", lambda: None)
        moved = Route.redirect("/old-photos", "/photos")
        gone = Route.permanent_redirect("/ancient", "/photos")
        page = Route.view("/about", "about")
        catch_all = Route.fallback(lambda: None)

        self.info("verbs and shapes")
        self._describe(index, head, matched, anything, moved, gone, page, catch_all)
        # A GET route answers HEAD too, which is why `route:list` prints both.
        self.line(f"    get answers      -> {'|'.join(index.methods)}")
        self.line(f"    any answers      -> {len(anything.methods)} verbs")
        self.line(f"    redirect status  -> {moved.action.status} / {gone.action.status}")

    def _constraints(self) -> None:
        self._fresh()
        numbered = Route.get("/users/{id}", lambda: None).where_number("id")
        slugged = Route.get("/slugs/{slug}", lambda: None).where("slug", r"[a-z-]+")
        listed = Route.get("/sizes/{size}", lambda: None).where_in("size", ["s", "m", "l"])
        uuid = Route.get("/tokens/{token}", lambda: None).where_uuid("token")
        optional = Route.get("/greet/{name?}", lambda: None).name("greet")

        Route.pattern("account", r"[0-9]+")
        patterned = Route.get("/accounts/{account}", lambda: None)

        self.info("parameter constraints")
        self.line(f"    where_number     -> {numbered.wheres}")
        self.line(f"    where            -> {slugged.wheres}")
        self.line(f"    where_in         -> {listed.wheres['size']}")
        self.line(f"    where_uuid       -> {uuid.wheres['token'][:24]}…")
        self.line(f"    global pattern   -> {patterned.wheres}")
        # Starlette has no optional segment, so an optional parameter compiles
        # to two paths and the handler's own default fills the shorter one.
        self.line(f"    optional {{name?}}  -> {list(optional.compiled_uris())}")

    def _groups(self) -> None:
        self._fresh()
        with Route.group(
            prefix="/admin",
            name="admin.",
            middleware=["auth"],
            controller=PhotoController,
            domain="{account}.almasix.test",
        ):
            photos = Route.get("/photos", "index").name("photos")
            with Route.group(prefix="/trash", middleware=["can:restore"]):
                trash = Route.get("/photos", "index").name("trash")

        self.info("groups")
        for entry in (photos, trash):
            self.line(f"    {entry.uri:26} {entry.get_name():14} {entry.middleware_names}")
        self.line(f"    domain           -> {photos.get_domain()}")
        self.line(f"    controller       -> {photos.action_name()}")

    # -- resources -----------------------------------------------------------

    def _resources(self) -> None:
        self.info("resource routing")

        full = self._fresh()
        Route.resource("photos", PhotoController)
        self.line(f"    resource         -> {len(full.routes)} routes")
        self._describe(*full.routes)

        api = self._fresh()
        Route.api_resource("photos", PhotoController)
        self.line(f"    api_resource     -> {[e.get_name() for e in api.routes]}")

        partial = self._fresh()
        Route.resource("photos", PhotoController).only("index", "show").names(
            {"index": "gallery"}
        ).parameters({"photos": "photo_id"})
        self.line(f"    only/names/params-> {[(e.uri, e.get_name()) for e in partial.routes]}")

        excepted = self._fresh()
        Route.resource("photos", PhotoController).except_("create", "edit", "destroy")
        self.line(f"    except_          -> {[e.get_name() for e in excepted.routes]}")

        nested = self._fresh()
        Route.resource("photos.comments", CommentController).only("index", "show")
        self.line(f"    nested           -> {[e.uri for e in nested.routes]}")

        shallow = self._fresh()
        Route.resource("photos.comments", CommentController).only("index", "show").shallow()
        self.line(f"    shallow          -> {[e.uri for e in shallow.routes]}")
        self.line(f"    shallow names    -> {[e.get_name() for e in shallow.routes]}")

        scoped = self._fresh()
        Route.resource("photos.comments", CommentController).only("show").scoped(
            {"comment": "slug"}
        )
        self.line(f"    scoped           -> {scoped.routes[0].uri}")

        prefixed = self._fresh()
        Route.api_resource("api/tags", PhotoController).only("index")
        entry = prefixed.routes[0]
        # A slash is where the resource lives, not part of what it is called.
        self.line(f"    a slash prefixes -> {entry.uri} named {entry.get_name()}")

        guarded = self._fresh()
        Route.resource("photos", PhotoController).only("show", "destroy").middleware(
            {"destroy": "can:delete"}
        ).missing(lambda request: None).with_trashed(["show"])
        for route_definition in guarded.routes:
            self.line(
                f"    {route_definition.get_name():16} "
                f"middleware={route_definition.middleware_names} "
                f"trashed={route_definition.trashed} "
                f"missing={route_definition.missing_handler is not None}"
            )

        localized = self._fresh()
        original = resource_verbs()
        try:
            set_resource_verbs(create="crear", edit="editar")
            Route.resource("fotos", PhotoController).only("create", "edit")
            self.line(f"    localized verbs  -> {[e.uri for e in localized.routes]}")
        finally:
            set_resource_verbs(**original)

    def _singletons(self) -> None:
        single = self._fresh()
        Route.singleton("profile", PhotoController)
        creatable = self._fresh()
        Route.api_singleton("settings", PhotoController).creatable()

        self.info("singleton resources")
        self.line("    singleton")
        self._describe(*single.routes)
        self.line("    api_singleton().creatable()")
        self._describe(*creatable.routes)

    # -- binding -------------------------------------------------------------

    def _binding(self) -> None:
        bound = self._fresh()
        Route.get("/articles/{article}", lambda article: None).name("articles.show")
        field = Route.get("/posts/{post:slug}", lambda post: None)
        missing = Route.get("/gone/{article}", lambda article: None).missing(lambda request: None)
        trashed = Route.get("/trashed/{article}", lambda article: None).with_trashed()

        Route.model("article", Article)
        Route.bind("uppercase", lambda value: value.upper())

        self.info("model binding")
        self.line(f"    route key        -> Article.{route_key_name(Article)}")
        self.line(f"    binding field    -> {field.binding_fields()}")
        self.line(f"    missing handler  -> {missing.missing_handler is not None}")
        self.line(f"    with_trashed     -> {trashed.trashed}")
        self.line(f"    Route.model      -> {sorted(bound._models)}")
        self.line(f"    Route.bind       -> {sorted(bound._binders)}")

    # -- URL generation ------------------------------------------------------

    def _urls(self) -> None:
        self._fresh()
        Route.get("/photos", [PhotoController, "index"]).name("photos.index")
        Route.get("/greet/{name?}", lambda: None).name("greet")

        self.info("URL generation")
        self.line(f"    url()            -> {url('/dashboard')}")
        self.line(f"    asset-style path -> {url('build/app.css')}")
        self.line(f"    route()          -> {route('photos.index')}")
        self.line(f"    a scalar         -> {route('greet', 'ada')}")
        self.line(f"    a list           -> {route('greet', ['ada'])}")
        self.line(f"    a mapping        -> {route('greet', {'name': 'ada'})}")
        self.line(f"    a keyword        -> {route('greet', name='ada')}")
        self.line(f"    a model          -> {route('greet', Article('ada'))}")
        self.line(f"    leftovers query  -> {route('photos.index', {'page': 2})}")
        self.line(f"    relative         -> {route('greet', 'ada', absolute=False)}")
        self.line(f"    optional omitted -> {route('greet')}")
        self.line(f"    action()         -> {action([PhotoController, 'index'])}")

    def _signing(self) -> None:
        self._fresh()
        Route.get("/photos", [PhotoController, "index"]).name("photos.index")

        signed = signed_route("photos.index")
        temporary = temporary_signed_route("photos.index", 30)
        relative = signed_route("photos.index", absolute=False)
        edited = signed.replace("/photos", "/albums")
        expired = sign(url("/photos"), expires_at=1)

        self.info("signed URLs")
        self.line(f"    signed_route     -> valid={has_valid_signature(signed)}")
        self.line(f"    temporary        -> carries expires={'expires=' in temporary}")
        self.line(f"    relative         -> valid={has_valid_relative_signature(relative)}")
        self.line(f"    edited           -> valid={has_valid_signature(edited)}")
        self.line(f"    expired          -> valid={has_valid_signature(expired)}")
        # The signature is still the right one; only the deadline passed, and
        # the two answers are what let a handler tell the user which it was.
        self.line(
            f"    expired, ignored -> valid={has_valid_signature(expired, ignore_expiry=True)}"
        )
        self.line("    middleware       -> Route.get(...).middleware('signed') answers 403")

    def _defaults(self) -> None:
        self._fresh()
        Route.get("/photos", [PhotoController, "index"]).name("photos.index")
        Route.get("/{locale}/help", lambda locale: None).name("localized.help")
        generator = UrlGenerator.from_config()

        self.info("URL defaults")
        try:
            generator.defaults({"locale": "en"})
            self.line(f"    default filled   -> {route('localized.help')}")
            self.line(f"    explicit wins    -> {route('localized.help', locale='fr')}")
            # A default fills a parameter a URI names and nothing else, so it
            # never turns up as `?locale=en` on an unrelated route.
            self.line(f"    no query spill   -> {route('photos.index')}")
        finally:
            generator.forget_defaults()
        self.line(f"    forgotten        -> {generator.defaults()}")
        self.line("    per request      -> the url.defaults middleware scopes them")

    def _current(self) -> None:
        router = self._fresh()
        Route.get("/photos", [PhotoController, "index"]).name("photos.index")

        self.info("the current route")
        self.line(f"    outside a request-> {Route.current()}")
        self.line(f"    Route.has        -> {Route.has('photos.index')}")
        self.line(f"    named routes     -> {sorted(router.named_routes())}")
        self.line("    route:list       -> smith route:list --middleware --sort=name")
