"""URL generation honoring `APP_URL` and `APP_BASE_PATH`.

Apps hosted under a subpath (`/apps/foo`) must never emit root-absolute links,
so every generated URL runs through here. The HTTP kernel mounts the ASGI app
at the same prefix so `smith serve` matches what `url()` emits.

`route()` is the reason names exist: a URI written once in `routes/web.py` and
read everywhere else means moving `/posts/{post}` to `/blog/{post}` is one
edit. Parameters the URI names are substituted; the rest become the query
string, which is Laravel's rule and the one that makes pagination links work.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from contextvars import ContextVar
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from almasix.aliases import install_camel_aliases
from almasix.config import config
from almasix.routing.constraints import PARAMETER_RE
from almasix.routing.signing import (
    expiry_from,
    has_valid_relative_signature,
    has_valid_signature,
    sign,
)

_ABSOLUTE_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*:)?//")

#: Values `URL::defaults` supplies for parameters a call did not pass, set
#: once for the whole application — in a service provider, say.
_app_defaults: dict[str, Any] = {}

#: The same, for one request only. Laravel keeps defaults on a singleton, which
#: is safe because a PHP process serves one request at a time. An ASGI process
#: serves many at once, so a `{locale}` read off *this* request must not leak
#: into the links another request is generating on another task.
_request_defaults: ContextVar[dict[str, Any] | None] = ContextVar(
    "almasix_url_defaults", default=None
)

#: Set by `force_scheme`, which a proxy that terminates TLS makes necessary.
_forced_scheme: str | None = None


def current_defaults() -> dict[str, Any]:
    """The default parameters in force here: application-wide plus request."""
    return {**_app_defaults, **(_request_defaults.get() or {})}


def push_defaults(values: Mapping[str, Any]) -> Any:
    """Open a request-scoped overlay of default parameters.

    Returns a token for `pop_defaults`. Used by the `url.defaults` middleware
    so the values die with the request that supplied them.
    """
    return _request_defaults.set({**(_request_defaults.get() or {}), **dict(values)})


def pop_defaults(token: Any) -> None:
    """Close the overlay `push_defaults` opened."""
    _request_defaults.reset(token)


class RouteNotFound(RuntimeError):
    """A name was asked for that no route carries."""


class MissingRouteParameter(RuntimeError):
    """A route's URI names a parameter the call did not supply."""


def _normalize_root(root: str) -> str:
    return root.strip().rstrip("/")


def _normalize_base(base: str) -> str:
    base = base.strip().strip("/")
    return f"/{base}" if base else ""


class UrlGenerator:
    """Builds URLs from a canonical origin plus a public path prefix."""

    def __init__(self, root: str = "", base_path: str = "") -> None:
        self.root = _normalize_root(root)
        self.base_path = _normalize_base(base_path)

    @classmethod
    def from_config(cls) -> UrlGenerator:
        """The generator this application's `APP_URL` describes.

        With no application booted — a script, a unit test — there is no
        `APP_URL` and no base path to honor, so the relative URL a rootless
        generator emits is the correct answer rather than a crash.
        """
        try:
            return cls(
                root=str(config("app.url", "") or ""),
                base_path=str(config("app.base_path", "") or ""),
            )
        except RuntimeError:
            return cls()

    # -- paths ---------------------------------------------------------------

    def to(
        self,
        path: str = "/",
        parameters: Sequence[Any] | Mapping[str, Any] | None = None,
        *,
        absolute: bool = True,
        secure: bool | None = None,
        query: Mapping[str, Any] | None = None,
    ) -> str:
        """A URL for ``path``, with extra segments and a query string.

        ``parameters`` appends path segments, as Laravel's second argument
        does; ``query`` is the query string, which Laravel spells with the
        fluent `withQuery`.
        """
        if _ABSOLUTE_RE.match(path):
            return _with_query(path, query)

        suffix = str(path).strip()
        for value in _segments(parameters):
            suffix = f"{suffix.rstrip('/')}/{quote(str(value), safe='')}"
        suffix = f"/{suffix.lstrip('/')}" if suffix.strip("/") else ""
        full = f"{self.base_path}{suffix}" or "/"
        if not absolute:
            return _with_query(full, query)
        return _with_query(self._with_root(full, secure=secure), query)

    def secure(
        self,
        path: str = "/",
        parameters: Sequence[Any] | Mapping[str, Any] | None = None,
        *,
        query: Mapping[str, Any] | None = None,
    ) -> str:
        """`to` over HTTPS whatever `APP_URL` says (Laravel ``secure``)."""
        return self.to(path, parameters, absolute=True, secure=True, query=query)

    def asset(self, path: str, *, absolute: bool = True, secure: bool | None = None) -> str:
        """Public URL for a file under ``public/`` (subpath-aware).

        Default apps ship Vite + Tailwind emitting into ``public/build/``.
        Keep calling ``asset(...)`` for any file under ``public/``.
        """
        return self.to(path, absolute=absolute, secure=secure)

    def secure_asset(self, path: str) -> str:
        return self.asset(path, absolute=True, secure=True)

    def _with_root(self, full: str, *, secure: bool | None = None) -> str:
        root = self.root
        if not root:
            return full
        scheme = "https" if secure else (None if secure is None else "http")
        scheme = scheme or _forced_scheme
        if scheme:
            parts = urlsplit(root)
            root = urlunsplit((scheme, parts.netloc or parts.path, "", "", "")).rstrip("/")
        return f"{root}{full}"

    # -- named routes --------------------------------------------------------

    def route(
        self,
        name: str,
        parameters: Mapping[str, Any] | Sequence[Any] | Any = None,
        /,
        *,
        absolute: bool = True,
        secure: bool | None = None,
        **named: Any,
    ) -> str:
        """The URL of a named route (Laravel ``route``).

        Parameters the URI names are substituted into it; anything left over
        becomes the query string. A single scalar fills a single-parameter
        route, and a model is read for its route key.
        """
        route = self._find(name)
        values = _parameter_values(parameters, named, route)
        path, leftover = _substitute(route.uri, values, _route_defaults(route))
        return self.to(path, absolute=absolute, secure=secure, query=leftover or None)

    def signed_route(
        self,
        name: str,
        parameters: Mapping[str, Any] | Sequence[Any] | Any = None,
        /,
        *,
        expiration: float | None = None,
        absolute: bool = True,
        **named: Any,
    ) -> str:
        """A named route's URL with a signature nobody can forge."""
        target = self.route(name, parameters, absolute=absolute, **named)
        expires = expiry_from(expiration) if expiration is not None else None
        return sign(target, expires_at=expires, absolute=absolute)

    def temporary_signed_route(
        self,
        name: str,
        expiration: float,
        parameters: Mapping[str, Any] | Sequence[Any] | Any = None,
        /,
        *,
        absolute: bool = True,
        **named: Any,
    ) -> str:
        """`signed_route` that stops working after ``expiration`` minutes."""
        return self.signed_route(
            name,
            parameters,
            expiration=expiration,
            absolute=absolute,
            **named,
        )

    def has_valid_signature(self, url: str, *, absolute: bool = True) -> bool:
        return has_valid_signature(url, absolute=absolute)

    def has_valid_relative_signature(self, url: str) -> bool:
        return has_valid_relative_signature(url)

    def action(
        self,
        action: Any,
        parameters: Mapping[str, Any] | Sequence[Any] | Any = None,
        /,
        *,
        absolute: bool = True,
        **named: Any,
    ) -> str:
        """The URL of a controller action (Laravel ``action``).

        Takes `[Controller, "method"]`, `"Controller@method"`, or a callable —
        the same shapes a route registration takes.
        """
        from almasix.routing.router import describe_action, get_router

        wanted = describe_action(action)
        for route in get_router().routes:
            if route.action_name() == wanted or route.action_name().endswith(f".{wanted}"):
                values = _parameter_values(parameters, named, route)
                path, leftover = _substitute(route.uri, values, _route_defaults(route))
                return self.to(path, absolute=absolute, query=leftover or None)
        raise RouteNotFound(f"No route is registered for the action {wanted!r}.")

    def _find(self, name: str) -> Any:
        from almasix.routing.router import get_router

        route = get_router().route_named(name)
        if route is None:
            known = ", ".join(sorted(get_router().named_routes())) or "nothing"
            raise RouteNotFound(f"No route is named {name!r}. Named routes: {known}.")
        return route

    # -- the current request -------------------------------------------------

    def current(self) -> str:
        """This request's URL without its query string (Laravel ``current``)."""
        return self.full().split("?", 1)[0]

    def full(self) -> str:
        """This request's URL, query string included (Laravel ``full``)."""
        request = _request()
        if request is None:
            return self.to("/")
        return str(request.url)

    def previous(self, fallback: str | bool = False) -> str:
        """The URL the request came from (Laravel ``previous``)."""
        request = _request()
        referer = request.header("referer") if request is not None else None
        if referer:
            return str(referer)
        if isinstance(fallback, str) and fallback:
            return self.to(fallback)
        return self.to("/")

    def previous_path(self, fallback: str | bool = False) -> str:
        """`previous` without the origin (Laravel ``previousPath``)."""
        path = urlsplit(self.previous(fallback)).path or "/"
        return path

    def query(
        self,
        path: str,
        parameters: Mapping[str, Any] | None = None,
        *,
        absolute: bool = True,
    ) -> str:
        """`to` with a query string merged onto whatever ``path`` carries."""
        return self.to(path, absolute=absolute, query=parameters)

    # -- configuration -------------------------------------------------------

    def defaults(self, values: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Values for parameters a `route()` call does not pass.

        A localized application prefixes every route with `{locale}` and would
        otherwise have to pass it at every call site. Only parameters a URI
        actually names are filled — a default never becomes a query string.

        Called inside a request opened by the `url.defaults` middleware, this
        writes to that request's overlay; otherwise it writes application-wide.
        """
        if values is not None:
            scoped = _request_defaults.get()
            if scoped is not None:
                scoped.update(dict(values))
            else:
                _app_defaults.update(dict(values))
        return current_defaults()

    def forget_defaults(self) -> None:
        """Drop the default parameters set application-wide."""
        _app_defaults.clear()

    def force_scheme(self, scheme: str | None) -> None:
        """Generate every absolute URL with this scheme (Laravel ``forceScheme``)."""
        global _forced_scheme
        _forced_scheme = scheme.rstrip(":/") if scheme else None

    def force_root_url(self, root: str | None) -> None:
        """Override `APP_URL` for the URLs this generator emits."""
        self.root = _normalize_root(root or "")


install_camel_aliases(UrlGenerator)


# -- module-level helpers ----------------------------------------------------


def url(
    path: str = "/",
    parameters: Sequence[Any] | Mapping[str, Any] | None = None,
    *,
    absolute: bool = True,
    secure: bool | None = None,
    query: Mapping[str, Any] | None = None,
) -> str:
    """Generate a URL for `path`, prefixed with `APP_BASE_PATH`."""
    return UrlGenerator.from_config().to(
        path, parameters, absolute=absolute, secure=secure, query=query
    )


def asset(path: str, *, absolute: bool = True) -> str:
    """Generate a URL for a static asset."""
    return UrlGenerator.from_config().asset(path, absolute=absolute)


def secure_url(path: str = "/", parameters: Sequence[Any] | None = None) -> str:
    """`url` over HTTPS (Laravel ``secure_url``)."""
    return UrlGenerator.from_config().secure(path, parameters)


def secure_asset(path: str) -> str:
    """`asset` over HTTPS (Laravel ``secure_asset``)."""
    return UrlGenerator.from_config().secure_asset(path)


def route(
    name: str,
    parameters: Mapping[str, Any] | Sequence[Any] | Any = None,
    /,
    *,
    absolute: bool = True,
    **named: Any,
) -> str:
    """The URL of a named route (Laravel ``route``)."""
    return UrlGenerator.from_config().route(name, parameters, absolute=absolute, **named)


def to_route(
    name: str,
    parameters: Mapping[str, Any] | Sequence[Any] | Any = None,
    /,
    *,
    status: int = 302,
    **named: Any,
) -> Any:
    """Redirect to a named route (Laravel ``to_route``)."""
    from almasix.http.response import Redirect

    return Redirect(route(name, parameters, absolute=False, **named), status_code=status)


def action(
    handler: Any,
    parameters: Mapping[str, Any] | Sequence[Any] | Any = None,
    /,
    *,
    absolute: bool = True,
    **named: Any,
) -> str:
    """The URL of a controller action (Laravel ``action``)."""
    return UrlGenerator.from_config().action(handler, parameters, absolute=absolute, **named)


def to_action(
    handler: Any,
    parameters: Mapping[str, Any] | Sequence[Any] | Any = None,
    /,
    *,
    status: int = 302,
    **named: Any,
) -> Any:
    """Redirect to a controller action (Laravel ``to_action``)."""
    from almasix.http.response import Redirect

    return Redirect(
        action(handler, parameters, absolute=False, **named),
        status_code=status,
    )


def signed_route(
    name: str,
    parameters: Mapping[str, Any] | Sequence[Any] | Any = None,
    /,
    *,
    expiration: float | None = None,
    absolute: bool = True,
    **named: Any,
) -> str:
    """A named route's URL, signed with `APP_KEY`."""
    return UrlGenerator.from_config().signed_route(
        name, parameters, expiration=expiration, absolute=absolute, **named
    )


def temporary_signed_route(
    name: str,
    expiration: float,
    parameters: Mapping[str, Any] | Sequence[Any] | Any = None,
    /,
    *,
    absolute: bool = True,
    **named: Any,
) -> str:
    """A signed URL that stops working after ``expiration`` minutes."""
    return UrlGenerator.from_config().temporary_signed_route(
        name, expiration, parameters, absolute=absolute, **named
    )


# -- internals ---------------------------------------------------------------


def _request() -> Any:
    from almasix.http.request import get_request

    return get_request()


def _segments(parameters: Sequence[Any] | Mapping[str, Any] | None) -> list[Any]:
    if parameters is None:
        return []
    if isinstance(parameters, Mapping):
        return list(parameters.values())
    if isinstance(parameters, (str, bytes)):
        return [parameters]
    return list(parameters)


def _with_query(target: str, query: Mapping[str, Any] | None) -> str:
    if not query:
        return target
    parts = urlsplit(target)
    pairs = parse_qsl(parts.query)
    for key, value in query.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            pairs.extend((key, str(item)) for item in value)
        else:
            pairs.append((key, str(value)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(pairs), parts.fragment))


def _parameter_values(
    parameters: Mapping[str, Any] | Sequence[Any] | Any,
    named: Mapping[str, Any],
    route: Any,
) -> dict[str, Any]:
    """Normalize every shape a caller may pass into one mapping.

    `route("posts.show", post)`, `route("posts.show", 7)`,
    `route("posts.show", [7])`, `route("posts.show", {"post": 7})`, and
    `route("posts.show", post=7)` all mean the same thing.
    """
    values: dict[str, Any] = {}
    expected = route.parameter_names()

    if parameters is None:
        pass
    elif isinstance(parameters, Mapping):
        values.update(dict(parameters))
    elif isinstance(parameters, (list, tuple)):
        values.update(dict(zip(expected, parameters, strict=False)))
        extra = list(parameters)[len(expected) :]
        # Laravel appends leftover positional values as path segments; here a
        # count that does not match the URI is far more likely a mistake.
        if extra:
            raise MissingRouteParameter(
                f"Route {route.route_name!r} takes {len(expected)} parameter(s) "
                f"({', '.join(expected) or 'none'}), and {len(parameters)} were passed."
            )
    elif expected:
        values[expected[0]] = parameters
    values.update(dict(named))
    return values


def _substitute(
    uri: str,
    values: Mapping[str, Any],
    defaults: Mapping[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Fill a URI's parameters, returning what is left for the query string."""
    used: set[str] = set()
    combined = {**(defaults or {}), **values}

    def replace(match: re.Match[str]) -> str:
        name = match.group("name")
        used.add(name)
        if name in combined and combined[name] is not None:
            return quote(str(_route_key(combined[name])), safe="")
        if match.group("optional"):
            return ""
        raise MissingRouteParameter(
            f"The URI {uri!r} names the parameter {name!r} and nothing supplied it."
        )

    path = PARAMETER_RE.sub(replace, uri)
    # `/user/{name?}` with no name must not leave `/user/` behind.
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/") or "/"
    path = path.replace("//", "/")
    leftover = {key: value for key, value in values.items() if key not in used}
    return path, leftover


def _route_defaults(route: Any) -> dict[str, Any]:
    """What may fill a parameter the call did not pass.

    A route's own `->defaults()` wins over the application-wide ones, being
    the more specific statement about that one URI.
    """
    return {**current_defaults(), **dict(route.default_values or {})}


def _route_key(value: Any) -> Any:
    """A model in a `route()` call means its route key (Laravel ``getRouteKey``)."""
    for attribute in ("get_route_key", "getRouteKey", "get_key"):
        getter = getattr(value, attribute, None)
        if callable(getter):
            return getter()
    return value
