"""Route definitions and router."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any


Action = Any  # [Controller, "method"] | Callable | "Controller@method"


@dataclass
class RouteDefinition:
    methods: tuple[str, ...]
    uri: str
    action: Action
    name: str | None = None
    middleware: list[str] = field(default_factory=list)

    def can(self, ability: str, model: str | type | None = None) -> RouteDefinition:
        """Append ``can`` middleware (Laravel ``Route::can``)."""
        if model is None:
            token = f"can:{ability}"
        elif isinstance(model, type):
            token = f"can:{ability},{model.__module__}.{model.__qualname__}"
        else:
            token = f"can:{ability},{model}"
        self.middleware.append(token)
        return self


@dataclass
class _GroupOptions:
    prefix: str = ""
    middleware: list[str] = field(default_factory=list)


class Router:
    """Collects route definitions with group / prefix / middleware support."""

    def __init__(self) -> None:
        self._routes: list[RouteDefinition] = []
        self._group_stack: list[_GroupOptions] = []

    @property
    def routes(self) -> list[RouteDefinition]:
        return list(self._routes)

    def add(
        self,
        methods: Sequence[str],
        uri: str,
        action: Action,
        *,
        name: str | None = None,
        middleware: Sequence[str] | None = None,
    ) -> RouteDefinition:
        prefix = "".join(group.prefix for group in self._group_stack)
        group_middleware: list[str] = []
        for group in self._group_stack:
            group_middleware.extend(group.middleware)

        normalized = uri if uri.startswith("/") else f"/{uri}"
        full_uri = f"{prefix.rstrip('/')}/{normalized.lstrip('/')}" if prefix else normalized
        if not full_uri.startswith("/"):
            full_uri = f"/{full_uri}"
        if full_uri != "/" and full_uri.endswith("/"):
            full_uri = full_uri.rstrip("/")

        route = RouteDefinition(
            methods=tuple(method.upper() for method in methods),
            uri=full_uri or "/",
            action=action,
            name=name,
            middleware=[*group_middleware, *(middleware or [])],
        )
        self._routes.append(route)
        return route

    def get(self, uri: str, action: Action, **kwargs: Any) -> RouteDefinition:
        return self.add(["GET"], uri, action, **kwargs)

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
        return self.add(
            ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            uri,
            action,
            **kwargs,
        )

    def match(
        self,
        methods: Sequence[str],
        uri: str,
        action: Action,
        **kwargs: Any,
    ) -> RouteDefinition:
        return self.add(methods, uri, action, **kwargs)

    @contextmanager
    def group(
        self,
        *,
        prefix: str = "",
        middleware: Sequence[str] | None = None,
    ) -> Iterator[None]:
        normalized_prefix = prefix
        if normalized_prefix and not normalized_prefix.startswith("/"):
            normalized_prefix = f"/{normalized_prefix}"
        self._group_stack.append(
            _GroupOptions(
                prefix=normalized_prefix,
                middleware=list(middleware or []),
            )
        )
        try:
            yield
        finally:
            self._group_stack.pop()


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
    def match(methods: Sequence[str], uri: str, action: Action, **kwargs: Any) -> RouteDefinition:
        return get_router().match(methods, uri, action, **kwargs)

    @staticmethod
    @contextmanager
    def group(
        *,
        prefix: str = "",
        middleware: Sequence[str] | None = None,
    ) -> Iterator[None]:
        with get_router().group(prefix=prefix, middleware=middleware):
            yield
