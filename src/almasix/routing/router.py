"""Route definitions and router.

The DSL is Laravel's, with two shapes Python asks for. Laravel's fluent
`Route::get(...)->name('x')->middleware('auth')` works here too, and so does
`Route::get(..., name="x")`, because a keyword argument is what a Python reader
expects. Groups are context managers rather than closures for the same reason:
`with Route.group(prefix="/admin"):` needs no lambda.

`name` and `middleware` are *methods*, so the stored values live on
`route_name` and `middleware_names`. Reading `route.name` and calling
`route.name("x")` cannot both work, and Laravel's spelling won.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from almasix.aliases import install_camel_aliases
from almasix.routing.constraints import (
    ALPHA_NUMERIC_PATTERN,
    ALPHA_PATTERN,
    NUMBER_PATTERN,
    ULID_PATTERN,
    UUID_PATTERN,
    binding_fields,
    compile_uri,
    in_pattern,
    parameter_names,
)

Action = Any  # [Controller, "method"] | Callable | "Controller@method"

#: Every verb a route may answer. HEAD rides with GET, as it does in Laravel.
VERBS = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")


@dataclass
class RouteDefinition:
    """One registered route, and the fluent surface that configures it."""

    methods: tuple[str, ...]
    uri: str
    action: Action
    route_name: str | None = None
    middleware_names: list[str] = field(default_factory=list)
    excluded_middleware: list[str] = field(default_factory=list)
    wheres: dict[str, str] = field(default_factory=dict)
    default_values: dict[str, Any] = field(default_factory=dict)
    domain_pattern: str | None = None
    missing_handler: Callable[..., Any] | None = None
    scoped_bindings: bool | None = None
    trashed: bool = False
    fallback: bool = False

    # -- naming --------------------------------------------------------------

    def name(self, name: str) -> RouteDefinition:
        """Name the route, appending to any name its group contributed."""
        self.route_name = f"{self.route_name or ''}{name}" or None
        _register_name(self)
        return self

    def get_name(self) -> str | None:
        """The route's name (Laravel ``getName``)."""
        return self.route_name

    def named(self, *patterns: str) -> bool:
        """Whether the name matches any pattern, `*` allowed (Laravel ``named``)."""
        if self.route_name is None:
            return False
        from almasix.support import Str

        return any(Str.is_(pattern, self.route_name) for pattern in patterns)

    # -- middleware ----------------------------------------------------------

    def middleware(self, *names: str | Sequence[str]) -> RouteDefinition:
        """Add middleware to the route (Laravel ``middleware``)."""
        self.middleware_names.extend(_flatten(names))
        return self

    def without_middleware(self, *names: str | Sequence[str]) -> RouteDefinition:
        """Exempt the route from middleware a group or the stack applied."""
        self.excluded_middleware.extend(_flatten(names))
        return self

    def gather_middleware(self) -> list[str]:
        """The middleware that actually runs, exclusions removed."""
        excluded = set(self.excluded_middleware)
        return [
            name
            for name in self.middleware_names
            if name not in excluded and str(name).partition(":")[0] not in excluded
        ]

    def can(self, ability: str, model: str | type | None = None) -> RouteDefinition:
        """Append ``can`` middleware (Laravel ``Route::can``)."""
        if model is None:
            token = f"can:{ability}"
        elif isinstance(model, type):
            token = f"can:{ability},{model.__module__}.{model.__qualname__}"
        else:
            token = f"can:{ability},{model}"
        self.middleware_names.append(token)
        return self

    # -- parameter constraints ----------------------------------------------

    def where(self, name: str | Mapping[str, str], pattern: str | None = None) -> RouteDefinition:
        """Constrain parameters by regex (Laravel ``where``).

        Takes one name and a pattern, or a mapping of both.
        """
        if isinstance(name, Mapping):
            self.wheres.update({str(key): str(value) for key, value in name.items()})
        else:
            if pattern is None:
                raise TypeError("where(name, pattern) needs a pattern.")
            self.wheres[name] = pattern
        return self

    def where_number(self, *names: str | Sequence[str]) -> RouteDefinition:
        return self._where_all(names, NUMBER_PATTERN)

    def where_alpha(self, *names: str | Sequence[str]) -> RouteDefinition:
        return self._where_all(names, ALPHA_PATTERN)

    def where_alpha_numeric(self, *names: str | Sequence[str]) -> RouteDefinition:
        return self._where_all(names, ALPHA_NUMERIC_PATTERN)

    def where_uuid(self, *names: str | Sequence[str]) -> RouteDefinition:
        return self._where_all(names, UUID_PATTERN)

    def where_ulid(self, *names: str | Sequence[str]) -> RouteDefinition:
        return self._where_all(names, ULID_PATTERN)

    def where_in(self, name: str, values: Iterable[Any]) -> RouteDefinition:
        """Constrain a parameter to a fixed set of values."""
        return self.where(name, in_pattern(values))

    def _where_all(self, names: Sequence[Any], pattern: str) -> RouteDefinition:
        for name in _flatten(names):
            self.where(str(name), pattern)
        return self

    # -- binding -------------------------------------------------------------

    def defaults(self, name: str | Mapping[str, Any], value: Any = None) -> RouteDefinition:
        """A value for a parameter the URL did not carry (Laravel ``defaults``)."""
        if isinstance(name, Mapping):
            self.default_values.update(dict(name))
        else:
            self.default_values[name] = value
        return self

    def missing(self, handler: Callable[..., Any]) -> RouteDefinition:
        """What to answer when implicit binding finds nothing."""
        self.missing_handler = handler
        return self

    def scope_bindings(self) -> RouteDefinition:
        """Resolve a nested parameter through its parent's relationship."""
        self.scoped_bindings = True
        return self

    def without_scoped_bindings(self) -> RouteDefinition:
        """Resolve every parameter independently, even when nested."""
        self.scoped_bindings = False
        return self

    def with_trashed(self, trashed: bool = True) -> RouteDefinition:
        """Let implicit binding find soft-deleted models."""
        self.trashed = bool(trashed)
        return self

    def binding_fields(self) -> dict[str, str]:
        """`{user:slug}` -> ``{"user": "slug"}``."""
        return binding_fields(self.uri)

    # -- domain --------------------------------------------------------------

    def domain(self, domain: str) -> RouteDefinition:
        """Answer only on this host, `{subdomain}` parameters included."""
        self.domain_pattern = domain
        return self

    def get_domain(self) -> str | None:
        return self.domain_pattern

    # -- reading -------------------------------------------------------------

    def parameter_names(self) -> list[str]:
        """Every parameter in the URI, in order."""
        return parameter_names(self.uri)

    def compiled_uris(self) -> tuple[str, ...]:
        """The Starlette paths this route registers as."""
        return compile_uri(self.uri, self.wheres)

    def action_name(self) -> str:
        """A readable name for the handler (what `route:list` prints)."""
        return describe_action(self.action)

    def __repr__(self) -> str:  # pragma: no cover — debugging aid
        methods = "|".join(self.methods)
        return f"<Route {methods} {self.uri} name={self.route_name!r}>"


install_camel_aliases(RouteDefinition)


@dataclass
class WebSocketRouteDefinition:
    """A websocket endpoint.

    Kept apart from HTTP routes because almost nothing about them is shared:
    no methods, no response, and a handler that lives for as long as the
    connection does.
    """

    uri: str
    action: Action
    route_name: str | None = None
    middleware_names: list[str] = field(default_factory=list)

    def name(self, name: str) -> WebSocketRouteDefinition:
        self.route_name = f"{self.route_name or ''}{name}" or None
        return self

    def get_name(self) -> str | None:
        return self.route_name

    def middleware(self, *names: str | Sequence[str]) -> WebSocketRouteDefinition:
        self.middleware_names.extend(_flatten(names))
        return self

    def gather_middleware(self) -> list[str]:
        return list(self.middleware_names)


@dataclass
class _GroupOptions:
    """One frame of the group stack — Laravel's group attributes."""

    prefix: str = ""
    middleware: list[str] = field(default_factory=list)
    excluded_middleware: list[str] = field(default_factory=list)
    name: str = ""
    domain: str | None = None
    controller: Any = None
    wheres: dict[str, str] = field(default_factory=dict)
    scoped_bindings: bool | None = None


class Router:
    """Collects route definitions with Laravel's group attributes."""

    def __init__(self) -> None:
        self._routes: list[RouteDefinition] = []
        self._websockets: list[WebSocketRouteDefinition] = []
        self._group_stack: list[_GroupOptions] = []
        self._patterns: dict[str, str] = {}
        self._binders: dict[str, Callable[[Any], Any]] = {}
        self._models: dict[str, tuple[type, Callable[[Any], Any] | None]] = {}
        self._fallback: RouteDefinition | None = None

    # -- reading -------------------------------------------------------------

    @property
    def routes(self) -> list[RouteDefinition]:
        """Every route, the fallback last so it only catches what nothing did."""
        routes = list(self._routes)
        if self._fallback is not None:
            routes.append(self._fallback)
        return routes

    @property
    def websocket_routes(self) -> list[WebSocketRouteDefinition]:
        return list(self._websockets)

    @property
    def fallback_route(self) -> RouteDefinition | None:
        return self._fallback

    def named_routes(self) -> dict[str, RouteDefinition]:
        """Every named route, by name."""
        return {route.route_name: route for route in self.routes if route.route_name is not None}

    def has(self, *names: str) -> bool:
        """Whether every name has a route (Laravel ``Route::has``)."""
        known = self.named_routes()
        return bool(names) and all(name in known for name in names)

    def route_named(self, name: str) -> RouteDefinition | None:
        return self.named_routes().get(name)

    # -- registration --------------------------------------------------------

    def add(
        self,
        methods: Sequence[str],
        uri: str,
        action: Action,
        *,
        name: str | None = None,
        middleware: Sequence[str] | None = None,
        where: Mapping[str, str] | None = None,
        defaults: Mapping[str, Any] | None = None,
        domain: str | None = None,
    ) -> RouteDefinition:
        group = self._merged_group()
        upper = tuple(method.upper() for method in methods)
        # A route answering GET answers HEAD, because a client asking only for
        # the headers of a page that exists should not be told it does not.
        # HEAD sits right after GET so `route:list` reads `GET|HEAD|POST`.
        if "GET" in upper and "HEAD" not in upper:
            index = upper.index("GET") + 1
            upper = (*upper[:index], "HEAD", *upper[index:])
        full_name = f"{group.name}{name}" if name is not None else (group.name or None)
        route = RouteDefinition(
            methods=upper,
            uri=self._full_uri(uri),
            action=self._resolve_group_action(action, group),
            route_name=full_name,
            middleware_names=[*group.middleware, *(middleware or [])],
            excluded_middleware=list(group.excluded_middleware),
            wheres={**self._patterns, **group.wheres, **(where or {})},
            default_values=dict(defaults or {}),
            domain_pattern=domain or group.domain,
            scoped_bindings=group.scoped_bindings,
        )
        self._routes.append(route)
        if route.route_name:
            _register_name(route)
        return route

    def websocket(
        self,
        uri: str,
        action: Action,
        *,
        name: str | None = None,
        middleware: Sequence[str] | None = None,
    ) -> WebSocketRouteDefinition:
        """Register a websocket endpoint (Laravel has none; ASGI gives us one)."""
        group = self._merged_group()
        route = WebSocketRouteDefinition(
            uri=self._full_uri(uri),
            action=self._resolve_group_action(action, group),
            route_name=f"{group.name}{name}" if name is not None else (group.name or None),
            middleware_names=[*group.middleware, *(middleware or [])],
        )
        self._websockets.append(route)
        return route

    # -- verbs ---------------------------------------------------------------

    def get(self, uri: str, action: Action, **kwargs: Any) -> RouteDefinition:
        return self.add(["GET"], uri, action, **kwargs)

    def head(self, uri: str, action: Action, **kwargs: Any) -> RouteDefinition:
        return self.add(["HEAD"], uri, action, **kwargs)

    def post(self, uri: str, action: Action, **kwargs: Any) -> RouteDefinition:
        return self.add(["POST"], uri, action, **kwargs)

    def put(self, uri: str, action: Action, **kwargs: Any) -> RouteDefinition:
        return self.add(["PUT"], uri, action, **kwargs)

    def patch(self, uri: str, action: Action, **kwargs: Any) -> RouteDefinition:
        return self.add(["PATCH"], uri, action, **kwargs)

    def delete(self, uri: str, action: Action, **kwargs: Any) -> RouteDefinition:
        return self.add(["DELETE"], uri, action, **kwargs)

    def options(self, uri: str, action: Action, **kwargs: Any) -> RouteDefinition:
        return self.add(["OPTIONS"], uri, action, **kwargs)

    def any(self, uri: str, action: Action, **kwargs: Any) -> RouteDefinition:
        """Answer every verb (Laravel ``any``)."""
        return self.add(VERBS, uri, action, **kwargs)

    def match(
        self,
        methods: Sequence[str] | str,
        uri: str,
        action: Action,
        **kwargs: Any,
    ) -> RouteDefinition:
        """Answer the listed verbs (Laravel ``match``)."""
        listed = [methods] if isinstance(methods, str) else list(methods)
        return self.add(listed, uri, action, **kwargs)

    # -- routes with no controller ------------------------------------------

    def redirect(
        self,
        uri: str,
        destination: str,
        status: int = 302,
        **kwargs: Any,
    ) -> RouteDefinition:
        """Redirect one URI to another without writing a controller."""
        return self.add(VERBS, uri, RedirectAction(destination, status), **kwargs)

    def permanent_redirect(self, uri: str, destination: str, **kwargs: Any) -> RouteDefinition:
        """`redirect` with a 301 (Laravel ``permanentRedirect``)."""
        return self.redirect(uri, destination, 301, **kwargs)

    def view(
        self,
        uri: str,
        template: str,
        data: Mapping[str, Any] | None = None,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> RouteDefinition:
        """Render a template without writing a controller (Laravel ``view``)."""
        return self.add(
            ["GET"],
            uri,
            ViewAction(template, dict(data or {}), status, dict(headers or {})),
            **kwargs,
        )

    def conduit(
        self,
        uri: str,
        component: str | type,
        *,
        layout: str | None = None,
        title: str | None = None,
        params: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> RouteDefinition:
        """Full-page Conduit component (Livewire ``Route::livewire``)."""
        from almasix.conduit.routing import mount_full_page

        return self.add(
            ["GET"],
            uri,
            mount_full_page(component, layout=layout, title=title, params=params),
            **kwargs,
        )

    def fallback(self, action: Action, **kwargs: Any) -> RouteDefinition:
        """Answer anything no other route matched (Laravel ``fallback``).

        Registered last no matter where it is declared, and a second call
        replaces the first — an application has one catch-all or none.
        """
        route = RouteDefinition(
            methods=VERBS,
            uri="/{fallback_placeholder:path}",
            action=action,
            route_name=kwargs.pop("name", None),
            middleware_names=[*self._merged_group().middleware, *(kwargs.pop("middleware", []))],
            fallback=True,
        )
        self._fallback = route
        if route.route_name:
            _register_name(route)
        return route

    # -- resources -----------------------------------------------------------

    def resource(self, name: str, controller: Any, **kwargs: Any) -> Any:
        """Seven routes for a CRUD resource (Laravel ``resource``)."""
        from almasix.routing.resource import PendingResourceRegistration

        return PendingResourceRegistration(self, name, controller, api_only=False, **kwargs)

    def api_resource(self, name: str, controller: Any, **kwargs: Any) -> Any:
        """`resource` without `create` and `edit`, which serve HTML forms."""
        from almasix.routing.resource import PendingResourceRegistration

        return PendingResourceRegistration(self, name, controller, api_only=True, **kwargs)

    def resources(self, mapping: Mapping[str, Any], **kwargs: Any) -> list[Any]:
        """Register many resources at once (Laravel ``resources``)."""
        return [self.resource(name, controller, **kwargs) for name, controller in mapping.items()]

    def api_resources(self, mapping: Mapping[str, Any], **kwargs: Any) -> list[Any]:
        return [
            self.api_resource(name, controller, **kwargs) for name, controller in mapping.items()
        ]

    def singleton(self, name: str, controller: Any, **kwargs: Any) -> Any:
        """A resource with no id — one `show`, one `edit`, one `update`."""
        from almasix.routing.resource import PendingSingletonRegistration

        return PendingSingletonRegistration(self, name, controller, api_only=False, **kwargs)

    def api_singleton(self, name: str, controller: Any, **kwargs: Any) -> Any:
        from almasix.routing.resource import PendingSingletonRegistration

        return PendingSingletonRegistration(self, name, controller, api_only=True, **kwargs)

    def singletons(self, mapping: Mapping[str, Any], **kwargs: Any) -> list[Any]:
        return [self.singleton(name, controller, **kwargs) for name, controller in mapping.items()]

    def api_singletons(self, mapping: Mapping[str, Any], **kwargs: Any) -> list[Any]:
        return [
            self.api_singleton(name, controller, **kwargs) for name, controller in mapping.items()
        ]

    # -- global patterns and explicit binding --------------------------------

    def pattern(self, name: str, expression: str) -> None:
        """Constrain a parameter everywhere it appears (Laravel ``pattern``)."""
        self._patterns[name] = expression

    def patterns(self, mapping: Mapping[str, str]) -> None:
        for name, expression in mapping.items():
            self.pattern(name, expression)

    @property
    def global_patterns(self) -> dict[str, str]:
        return dict(self._patterns)

    def bind(self, name: str, resolver: Callable[[Any], Any]) -> None:
        """Resolve a parameter with a callable (Laravel ``Route::bind``)."""
        self._binders[name] = resolver

    def model(
        self,
        name: str,
        model: type,
        missing: Callable[[Any], Any] | None = None,
    ) -> None:
        """Resolve a parameter to a model by key (Laravel ``Route::model``)."""
        self._models[name] = (model, missing)

    def binder_for(self, name: str) -> Callable[[Any], Any] | None:
        return self._binders.get(name)

    def model_for(self, name: str) -> tuple[type, Callable[[Any], Any] | None] | None:
        return self._models.get(name)

    # -- groups --------------------------------------------------------------

    @contextmanager
    def group(
        self,
        *,
        prefix: str = "",
        middleware: Sequence[str] | None = None,
        without_middleware: Sequence[str] | None = None,
        name: str = "",
        domain: str | None = None,
        controller: Any = None,
        where: Mapping[str, str] | None = None,
        scope_bindings: bool | None = None,
    ) -> Iterator[None]:
        """Share attributes with every route defined inside.

        A context manager rather than Laravel's closure, because Python has one
        and a nested `def` for two routes reads worse than a `with`.
        """
        normalized_prefix = prefix
        if normalized_prefix and not normalized_prefix.startswith("/"):
            normalized_prefix = f"/{normalized_prefix}"
        self._group_stack.append(
            _GroupOptions(
                prefix=normalized_prefix,
                middleware=list(middleware or []),
                excluded_middleware=list(without_middleware or []),
                name=name,
                domain=domain,
                controller=controller,
                wheres=dict(where or {}),
                scoped_bindings=scope_bindings,
            )
        )
        try:
            yield
        finally:
            self._group_stack.pop()

    def _merged_group(self) -> _GroupOptions:
        """Flatten the group stack, outermost first."""
        merged = _GroupOptions()
        for group in self._group_stack:
            merged.middleware.extend(group.middleware)
            merged.excluded_middleware.extend(group.excluded_middleware)
            merged.name = f"{merged.name}{group.name}"
            merged.wheres.update(group.wheres)
            if group.domain is not None:
                merged.domain = group.domain
            if group.controller is not None:
                merged.controller = group.controller
            if group.scoped_bindings is not None:
                merged.scoped_bindings = group.scoped_bindings
        return merged

    def _resolve_group_action(self, action: Action, group: _GroupOptions) -> Action:
        """A bare method name inside a `controller=` group names that method."""
        if group.controller is not None and isinstance(action, str) and "@" not in action:
            return [group.controller, action]
        return action

    def _full_uri(self, uri: str) -> str:
        prefix = "".join(group.prefix for group in self._group_stack)
        normalized = uri if uri.startswith("/") else f"/{uri}"
        full_uri = f"{prefix.rstrip('/')}/{normalized.lstrip('/')}" if prefix else normalized
        if not full_uri.startswith("/"):
            full_uri = f"/{full_uri}"
        if full_uri != "/" and full_uri.endswith("/"):
            full_uri = full_uri.rstrip("/")
        return full_uri or "/"

    def _group_middleware(self) -> list[str]:
        return list(self._merged_group().middleware)


class RedirectAction:
    """The action a `Route.redirect` registers."""

    def __init__(self, destination: str, status: int = 302) -> None:
        self.destination = destination
        self.status = status

    def __call__(self) -> Any:
        from almasix.http.response import redirect

        return redirect(self.destination, status=self.status)

    def __repr__(self) -> str:
        return f"redirect -> {self.destination} ({self.status})"


class ViewAction:
    """The action a `Route.view` registers."""

    def __init__(
        self,
        template: str,
        data: dict[str, Any],
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.template = template
        self.data = data
        self.status = status
        self.headers = headers or {}

    def __call__(self) -> Any:
        from almasix.prism.helpers import view

        return view(self.template, self.data, status=self.status, headers=self.headers)

    def __repr__(self) -> str:
        return f"view -> {self.template}"


def describe_action(action: Action) -> str:
    """A readable name for a route's handler."""
    if isinstance(action, (RedirectAction, ViewAction)):
        return repr(action)
    if isinstance(action, str):
        return action
    if isinstance(action, (list, tuple)) and len(action) == 2:
        controller, method = action
        name = controller.__name__ if isinstance(controller, type) else str(controller)
        return f"{name}@{method}"
    name = getattr(action, "__qualname__", None) or getattr(action, "__name__", None)
    return name or repr(action)


def _flatten(names: Sequence[Any]) -> list[str]:
    """`middleware("a", ["b", "c"])` and `middleware(["a"])` both work."""
    flat: list[str] = []
    for name in names:
        if isinstance(name, str):
            flat.append(name)
        elif isinstance(name, Iterable):
            flat.extend(str(item) for item in name)
        else:
            flat.append(str(name))
    return flat


def _register_name(route: RouteDefinition) -> None:
    """Names are read off the router, so this only guards against duplicates."""
    router = _router
    if router is None or route.route_name is None:
        return
    for other in router._routes:
        if other is not route and other.route_name == route.route_name:
            raise DuplicateRouteName(
                f"Two routes are named {route.route_name!r}: {other.uri} and {route.uri}. "
                "A name has to identify one route for route() to generate its URL."
            )


class DuplicateRouteName(RuntimeError):
    """Two routes claimed the same name."""


_router: Router | None = None


def set_router(router: Router | None) -> None:
    global _router
    _router = router


def get_router() -> Router:
    if _router is None:
        raise RuntimeError("Router is not set. Bootstrap the Application first.")
    return _router


class Route:
    """Static façade for registering routes on the active application router."""

    @staticmethod
    def get(uri: str, action: Action, **kwargs: Any) -> RouteDefinition:
        return get_router().get(uri, action, **kwargs)

    @staticmethod
    def head(uri: str, action: Action, **kwargs: Any) -> RouteDefinition:
        return get_router().head(uri, action, **kwargs)

    @staticmethod
    def post(uri: str, action: Action, **kwargs: Any) -> RouteDefinition:
        return get_router().post(uri, action, **kwargs)

    @staticmethod
    def put(uri: str, action: Action, **kwargs: Any) -> RouteDefinition:
        return get_router().put(uri, action, **kwargs)

    @staticmethod
    def patch(uri: str, action: Action, **kwargs: Any) -> RouteDefinition:
        return get_router().patch(uri, action, **kwargs)

    @staticmethod
    def delete(uri: str, action: Action, **kwargs: Any) -> RouteDefinition:
        return get_router().delete(uri, action, **kwargs)

    @staticmethod
    def options(uri: str, action: Action, **kwargs: Any) -> RouteDefinition:
        return get_router().options(uri, action, **kwargs)

    @staticmethod
    def any(uri: str, action: Action, **kwargs: Any) -> RouteDefinition:
        return get_router().any(uri, action, **kwargs)

    @staticmethod
    def match(
        methods: Sequence[str] | str,
        uri: str,
        action: Action,
        **kwargs: Any,
    ) -> RouteDefinition:
        return get_router().match(methods, uri, action, **kwargs)

    @staticmethod
    def redirect(uri: str, destination: str, status: int = 302, **kwargs: Any) -> RouteDefinition:
        return get_router().redirect(uri, destination, status, **kwargs)

    @staticmethod
    def permanent_redirect(uri: str, destination: str, **kwargs: Any) -> RouteDefinition:
        return get_router().permanent_redirect(uri, destination, **kwargs)

    @staticmethod
    def view(
        uri: str,
        template: str,
        data: Mapping[str, Any] | None = None,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> RouteDefinition:
        return get_router().view(uri, template, data, status, headers, **kwargs)

    @staticmethod
    def conduit(
        uri: str,
        component: str | type,
        *,
        layout: str | None = None,
        title: str | None = None,
        params: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> RouteDefinition:
        """Full-page Conduit component (Livewire ``Route::livewire``)."""
        return get_router().conduit(
            uri, component, layout=layout, title=title, params=params, **kwargs
        )

    @staticmethod
    def fallback(action: Action, **kwargs: Any) -> RouteDefinition:
        return get_router().fallback(action, **kwargs)

    @staticmethod
    def resource(name: str, controller: Any, **kwargs: Any) -> Any:
        return get_router().resource(name, controller, **kwargs)

    @staticmethod
    def api_resource(name: str, controller: Any, **kwargs: Any) -> Any:
        return get_router().api_resource(name, controller, **kwargs)

    @staticmethod
    def resources(mapping: Mapping[str, Any], **kwargs: Any) -> list[Any]:
        return get_router().resources(mapping, **kwargs)

    @staticmethod
    def api_resources(mapping: Mapping[str, Any], **kwargs: Any) -> list[Any]:
        return get_router().api_resources(mapping, **kwargs)

    @staticmethod
    def singleton(name: str, controller: Any, **kwargs: Any) -> Any:
        return get_router().singleton(name, controller, **kwargs)

    @staticmethod
    def api_singleton(name: str, controller: Any, **kwargs: Any) -> Any:
        return get_router().api_singleton(name, controller, **kwargs)

    @staticmethod
    def singletons(mapping: Mapping[str, Any], **kwargs: Any) -> list[Any]:
        return get_router().singletons(mapping, **kwargs)

    @staticmethod
    def api_singletons(mapping: Mapping[str, Any], **kwargs: Any) -> list[Any]:
        return get_router().api_singletons(mapping, **kwargs)

    @staticmethod
    def pattern(name: str, expression: str) -> None:
        get_router().pattern(name, expression)

    @staticmethod
    def patterns(mapping: Mapping[str, str]) -> None:
        get_router().patterns(mapping)

    @staticmethod
    def bind(name: str, resolver: Callable[[Any], Any]) -> None:
        get_router().bind(name, resolver)

    @staticmethod
    def model(name: str, model: type, missing: Callable[[Any], Any] | None = None) -> None:
        get_router().model(name, model, missing)

    @staticmethod
    def has(*names: str) -> bool:
        return get_router().has(*names)

    @staticmethod
    def websocket(uri: str, action: Action, **kwargs: Any) -> WebSocketRouteDefinition:
        return get_router().websocket(uri, action, **kwargs)

    @staticmethod
    def current() -> RouteDefinition | None:
        """The route answering this request (Laravel ``Route::current``)."""
        from almasix.http.request import get_request

        request = get_request()
        return getattr(request, "matched_route", None) if request is not None else None

    @staticmethod
    def current_route_name() -> str | None:
        route = Route.current()
        return route.route_name if route is not None else None

    @staticmethod
    def current_route_action() -> str | None:
        route = Route.current()
        return route.action_name() if route is not None else None

    @staticmethod
    def is_(*patterns: str) -> bool:
        """Whether the current route's name matches (Laravel ``Route::is``)."""
        route = Route.current()
        return route.named(*patterns) if route is not None else False

    @staticmethod
    @contextmanager
    def group(**kwargs: Any) -> Iterator[None]:
        with get_router().group(**kwargs):
            yield


install_camel_aliases(Route)
# `Route::is` is a keyword in Python, so the method is `is_` and the camelCase
# alias comes from Laravel's own spelling of the same idea.
Route.currentRouteName = Route.current_route_name  # type: ignore[attr-defined]
Route.currentRouteAction = Route.current_route_action  # type: ignore[attr-defined]
