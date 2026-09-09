"""Resource routing — seven routes from one line.

`Route.resource("photos", PhotoController)` registers Laravel's seven actions
with Laravel's URIs, names, and verbs. The registration is *pending*: the
routes land when the object is used or dropped, so the fluent methods
(`only`, `except_`, `names`, `shallow`) can still change them.

Python has no `except` as an identifier, so that one is `except_`. Laravel's
`->except([...])` spelling is aliased onto it, and both are documented.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from almasix.aliases import install_camel_aliases
from almasix.orm.inflector import singularize, snake

#: Laravel's seven, in the order `route:list` shows them.
RESOURCE_ACTIONS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("index", ("GET",), ""),
    ("create", ("GET",), "/create"),
    ("store", ("POST",), ""),
    ("show", ("GET",), "/{id}"),
    ("edit", ("GET",), "/{id}/edit"),
    ("update", ("PUT", "PATCH"), "/{id}"),
    ("destroy", ("DELETE",), "/{id}"),
)

#: The two that exist to serve an HTML form, and so have no place in an API.
FORM_ACTIONS = frozenset({"create", "edit"})

#: A singleton has no id, and cannot be listed or created by default.
SINGLETON_ACTIONS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("show", ("GET",), ""),
    ("edit", ("GET",), "/edit"),
    ("update", ("PUT", "PATCH"), ""),
)

CREATABLE_ACTIONS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("create", ("GET",), "/create"),
    ("store", ("POST",), ""),
)

DESTROYABLE_ACTION: tuple[str, tuple[str, ...], str] = ("destroy", ("DELETE",), "")

#: Laravel's `Route::resourceVerbs` — the two URI segments that are words.
_VERBS = {"create": "create", "edit": "edit"}


def resource_verbs() -> dict[str, str]:
    """The localizable URI verbs (Laravel ``Route::resourceVerbs``)."""
    return dict(_VERBS)


def set_resource_verbs(create: str | None = None, edit: str | None = None) -> None:
    """Translate `/create` and `/edit` for a non-English application."""
    if create is not None:
        _VERBS["create"] = create
    if edit is not None:
        _VERBS["edit"] = edit


class PendingResourceRegistration:
    """A resource whose routes are registered and still configurable.

    Laravel registers these from a destructor, so `Route::resource(...)` works
    as a bare statement and the fluent calls get a chance to change it first.
    Python can do better than depending on when an object is collected: the
    routes land immediately, and every fluent method rewrites them in place.
    So a bare `Route.resource("photos", ...)` needs nothing after it, and
    `.only("index")` on the next line is still honoured.
    """

    api_actions = RESOURCE_ACTIONS

    def __init__(
        self,
        router: Any,
        name: str,
        controller: Any,
        *,
        api_only: bool = False,
        only: Sequence[str] | None = None,
        except_: Sequence[str] | None = None,
        names: Mapping[str, str] | str | None = None,
        parameters: Mapping[str, str] | str | None = None,
        shallow: bool = False,
        middleware: Sequence[str] | None = None,
        where: Mapping[str, str] | None = None,
    ) -> None:
        self.router = router
        self.name = name.strip("/")
        self.controller = controller
        self.api_only = api_only
        self._only: list[str] | None = list(only) if only is not None else None
        self._except: list[str] = list(except_ or [])
        self._names: dict[str, str] = {}
        self._name_prefix: str | None = None
        self._parameters: dict[str, str] = {}
        self._parameter_default: str | None = None
        self._shallow = shallow
        self._scoped: dict[str, str] | None = None
        self._middleware: dict[str, list[str]] = {}
        self._shared_middleware = list(middleware or [])
        self._excluded_middleware: dict[str, list[str]] = {}
        self._where = dict(where or {})
        self._missing: Callable[..., Any] | None = None
        self._trashed: bool | list[str] = False
        self._registered: list[Any] = []

        if names is not None:
            self._name_prefix = names if isinstance(names, str) else self._name_prefix
            if not isinstance(names, str):
                self._names.update({str(k): str(v) for k, v in names.items()})
        if parameters is not None:
            if isinstance(parameters, str):
                self._parameter_default = parameters
            else:
                self._parameters.update({str(k): str(v) for k, v in parameters.items()})
        self._write()

    # -- fluent configuration ------------------------------------------------

    def only(self, *actions: str | Sequence[str]) -> PendingResourceRegistration:
        """Register only these actions (Laravel ``only``)."""
        self._only = _names(actions)
        return self._write()

    def except_(self, *actions: str | Sequence[str]) -> PendingResourceRegistration:
        """Register everything but these actions (Laravel ``except``)."""
        self._except = _names(actions)
        return self._write()

    def names(self, names: Mapping[str, str] | str) -> PendingResourceRegistration:
        """Rename the routes — a mapping per action, or one prefix for all."""
        if isinstance(names, str):
            self._name_prefix = names
        else:
            self._names.update({str(key): str(value) for key, value in names.items()})
        return self._write()

    def parameters(self, parameters: Mapping[str, str] | str) -> PendingResourceRegistration:
        """Rename the URI parameters (Laravel ``parameters``)."""
        if isinstance(parameters, str):
            self._parameter_default = parameters
        else:
            self._parameters.update({str(key): str(value) for key, value in parameters.items()})
        return self._write()

    def shallow(self, shallow: bool = True) -> PendingResourceRegistration:
        """Drop the parent segment from routes that already have a child id."""
        self._shallow = bool(shallow)
        return self._write()

    def scoped(self, bindings: Mapping[str, str] | None = None) -> PendingResourceRegistration:
        """Resolve a nested child through its parent, optionally by column."""
        self._scoped = {str(k): str(v) for k, v in (bindings or {}).items()}
        return self._write()

    def middleware(
        self,
        names: Sequence[str] | str | Mapping[str, Sequence[str] | str],
    ) -> PendingResourceRegistration:
        """Middleware for every action, or a mapping of action to middleware."""
        if isinstance(names, Mapping):
            for action, value in names.items():
                self._middleware.setdefault(str(action), []).extend(_names([value]))
        else:
            self._shared_middleware.extend(_names([names]))
        return self._write()

    def without_middleware(
        self,
        names: Sequence[str] | str | Mapping[str, Sequence[str] | str],
    ) -> PendingResourceRegistration:
        """Exempt actions from middleware (Laravel ``withoutMiddleware``)."""
        if isinstance(names, Mapping):
            for action, value in names.items():
                self._excluded_middleware.setdefault(str(action), []).extend(_names([value]))
        else:
            for action in self._actions_to_register():
                self._excluded_middleware.setdefault(action, []).extend(_names([names]))
        return self._write()

    def where(self, constraints: Mapping[str, str]) -> PendingResourceRegistration:
        self._where.update({str(k): str(v) for k, v in constraints.items()})
        return self._write()

    def missing(self, handler: Callable[..., Any]) -> PendingResourceRegistration:
        """What to answer when implicit binding finds nothing."""
        self._missing = handler
        return self._write()

    def with_trashed(self, actions: bool | Sequence[str] = True) -> PendingResourceRegistration:
        """Let binding find soft-deleted models, on all actions or some."""
        self._trashed = True if actions is True else _names([actions])
        return self._write()

    # -- registration --------------------------------------------------------

    @property
    def routes(self) -> list[Any]:
        """The routes this resource registered."""
        return list(self._registered)

    def register(self) -> list[Any]:
        """The routes, already registered. Kept for Laravel's spelling."""
        return list(self._registered)

    def _write(self) -> Any:
        """Replace this resource's routes with what the options now say.

        The routes are registered as soon as the resource is, so a bare
        `Route.resource(...)` works; a fluent call afterwards rewrites them
        rather than adding a second set.
        """
        self._retract()
        self._registered = [self._register_action(*spec) for spec in self._specs()]
        return self

    def _retract(self) -> None:
        registered = {id(route) for route in self._registered}
        if not registered:
            return
        self.router._routes[:] = [
            route for route in self.router._routes if id(route) not in registered
        ]
        self._registered = []

    def _specs(self) -> list[tuple[str, tuple[str, ...], str]]:
        wanted = self._actions_to_register()
        return [spec for spec in self._action_table() if spec[0] in wanted]

    def _action_table(self) -> tuple[tuple[str, tuple[str, ...], str], ...]:
        return RESOURCE_ACTIONS

    def _default_actions(self) -> list[str]:
        table = [action for action, _, _ in self._action_table()]
        if self.api_only:
            return [action for action in table if action not in FORM_ACTIONS]
        return table

    def _actions_to_register(self) -> list[str]:
        actions = self._only if self._only is not None else self._default_actions()
        return [action for action in actions if action not in self._except]

    def _register_action(self, action: str, methods: tuple[str, ...], suffix: str) -> Any:
        route = self.router.add(
            list(methods),
            self._uri_for(action, suffix),
            self._action_for(action),
            name=self._route_name(action),
            middleware=[*self._shared_middleware, *self._middleware.get(action, [])],
            where=self._where or None,
        )
        if self._excluded_middleware.get(action):
            route.without_middleware(self._excluded_middleware[action])
        if self._missing is not None:
            route.missing(self._missing)
        if self._trashed is True or (isinstance(self._trashed, list) and action in self._trashed):
            route.with_trashed()
        if self._scoped is not None:
            route.scope_bindings()
        return route

    def _action_for(self, action: str) -> Any:
        return [self.controller, action]

    # -- URIs ----------------------------------------------------------------

    @property
    def segments(self) -> list[str]:
        """`photos.comments` nests, so it is two segments, parent first.

        Only a dot nests. A slash is a literal prefix, so
        `api_resource("api/tags")` is one resource under `/api`, not a `tags`
        nested inside an `api`.
        """
        return [part for part in self.name.split(".") if part]

    def collection_uri(self) -> str:
        """`/photos/{photo}/comments` — where `index` and `store` answer."""
        parents = self.segments[:-1]
        prefix = "".join(f"/{name}/{{{self.parameter_for(name)}}}" for name in parents)
        return f"{prefix}/{self.segments[-1]}"

    def member_uri(self) -> str:
        """`/photos/{photo}/comments/{comment}` — one member of the resource.

        Under `shallow()` the parent falls away, because a comment id already
        identifies the comment and repeating the photo only invites the two to
        disagree.
        """
        placeholder = f"{{{self.member_parameter()}{self._binding_field()}}}"
        if self.is_shallow():
            return f"/{self.segments[-1].strip('/')}/{placeholder}"
        return f"{self.collection_uri()}/{placeholder}"

    def is_shallow(self) -> bool:
        """Shallow only means anything when there is a parent to drop."""
        return self._shallow and len(self.segments) > 1

    def _uri_for(self, action: str, suffix: str) -> str:
        if action in {"index", "store"}:
            return self.collection_uri()
        if action == "create":
            return f"{self.collection_uri()}/{_VERBS['create']}"
        if action == "edit":
            return f"{self.member_uri()}/{_VERBS['edit']}"
        if action in {"show", "update", "destroy"}:
            return self.member_uri()
        return f"{self.collection_uri()}{suffix}"  # pragma: no cover — table is closed

    def parameter_for(self, segment: str) -> str:
        """The parameter naming one member of ``segment``."""
        override = self._parameters.get(segment)
        return override or snake(singularize(segment.rsplit("/", 1)[-1]))

    def member_parameter(self) -> str:
        """The URI parameter for one member of the resource."""
        if self._parameter_default is not None:
            return self._parameter_default
        last = self.segments[-1]
        return (
            self._parameters.get(last)
            or self._parameters.get(self.name)
            or self.parameter_for(last)
        )

    def _binding_field(self) -> str:
        field = (self._scoped or {}).get(self.member_parameter())
        return f":{field}" if field else ""

    def _route_name(self, action: str) -> str:
        if action in self._names:
            return self._names[action]
        if self._name_prefix is not None:
            return f"{self._name_prefix}.{action}"
        # A shallow child is reachable without its parent, so its name says so.
        segments = self.segments[-1:] if self.is_shallow_action(action) else self.segments
        # A slash is a URI prefix and nothing more: `resource("api/tags")` is
        # named `tags.index`, as Laravel names it, because the `/api` is where
        # the resource lives rather than part of what it is called.
        return ".".join([*(part.rsplit("/", 1)[-1] for part in segments), action])

    def is_shallow_action(self, action: str) -> bool:
        return self.is_shallow() and action in {"show", "edit", "update", "destroy"}

    def __iter__(self) -> Any:
        return iter(self.routes)

    def __len__(self) -> int:
        return len(self.routes)


class PendingSingletonRegistration(PendingResourceRegistration):
    """A resource with exactly one member, so no id and no index."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._creatable = False
        self._destroyable = False
        super().__init__(*args, **kwargs)

    def creatable(self) -> PendingSingletonRegistration:
        """Add `create`, `store`, and `destroy` (Laravel ``creatable``)."""
        self._creatable = True
        self._destroyable = True
        return self._write()

    def destroyable(self) -> PendingSingletonRegistration:
        """Add `destroy` without `create` (Laravel ``destroyable``)."""
        self._destroyable = True
        return self._write()

    def _action_table(self) -> tuple[tuple[str, tuple[str, ...], str], ...]:
        table: list[tuple[str, tuple[str, ...], str]] = []
        if self._creatable:
            table.extend(CREATABLE_ACTIONS)
        table.extend(SINGLETON_ACTIONS)
        if self._destroyable:
            table.append(DESTROYABLE_ACTION)
        return tuple(table)

    def member_uri(self) -> str:
        """There is only one, so the URI is the collection's."""
        return self.collection_uri()


def _names(values: Sequence[Any]) -> list[str]:
    flat: list[str] = []
    for value in values:
        if isinstance(value, str):
            flat.append(value)
        elif isinstance(value, Iterable):
            flat.extend(str(item) for item in value)
        elif value is not None and not isinstance(value, bool):
            flat.append(str(value))
    return flat


install_camel_aliases(PendingResourceRegistration)
install_camel_aliases(PendingSingletonRegistration)
# `except` is a Python keyword, so it cannot be a method name — but it can be
# an attribute, which keeps `getattr(resource, "except")(...)` honest for
# anyone porting Laravel code line by line.
setattr(PendingResourceRegistration, "except", PendingResourceRegistration.except_)
