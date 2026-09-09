"""Route model binding — a path segment arrives as the model it names.

A controller that declares `async def show(self, post: Post)` should be handed
a `Post`, not the string `"7"`. Laravel calls that implicit binding, and the
rules it follows are the ones here:

* the parameter name has to match, so `/{post}` binds `post: Post`;
* the key is the model's route key, `id` unless it says otherwise;
* `{post:slug}` binds by that column instead;
* nothing found is a 404, or whatever the route's `missing()` returns;
* explicit `Route.model` / `Route.bind` win over the type hint.

Scoped bindings resolve a nested parameter *through* its parent, so
`/posts/{post}/comments/{comment}` cannot return a comment on another post.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from typing import Any

from almasix.http.exceptions import NotFoundHttpException


class BindingMissing(Exception):
    """Nothing matched, and the route said what to do about it.

    Carries the route's `missing()` handler so the kernel can answer with it
    rather than the 404 that would otherwise be right.
    """

    def __init__(self, handler: Callable[..., Any], parameter: str) -> None:
        super().__init__(f"No model bound for {parameter!r}.")
        self.handler = handler
        self.parameter = parameter


def route_key_name(model: type) -> str:
    """The column implicit binding looks a model up by."""
    for attribute in ("get_route_key_name", "getRouteKeyName"):
        getter = getattr(model, attribute, None)
        if callable(getter):
            try:
                return str(getter())
            except TypeError:
                # An instance method on the class, so there is no instance to
                # call it with; the primary key is the right answer anyway.
                break
    return str(getattr(model, "primary_key", "id") or "id")


def is_bindable(annotation: Any) -> bool:
    """Whether a type hint names something binding can resolve."""
    if not isinstance(annotation, type):
        return False
    import enum

    # Enums first: a backed enum *is* a `str` or `int` subclass, and
    # `Status(IntEnum)` is exactly the kind of parameter binding should fill.
    if issubclass(annotation, enum.Enum):
        return True
    if issubclass(annotation, (str, int, float, bool, bytes)):
        return False
    return hasattr(annotation, "query") or hasattr(annotation, "find")


async def resolve(
    annotation: type,
    value: Any,
    *,
    field: str | None = None,
    trashed: bool = False,
    parent: Any = None,
    relationship: str | None = None,
) -> Any:
    """Turn a path value into the model (or enum member) it names."""
    import enum

    if issubclass(annotation, enum.Enum):
        return _enum_member(annotation, value)

    key = field or route_key_name(annotation)
    if parent is not None and relationship is not None:
        found = await _scoped_lookup(parent, relationship, key, value, trashed=trashed)
    else:
        found = await _lookup(annotation, key, value, trashed=trashed)
    if found is None:
        from almasix.orm.builder import ModelNotFoundError

        raise ModelNotFoundError(f"No {annotation.__name__} with {key} {value!r}.")
    return found


def _enum_member(annotation: type, value: Any) -> Any:
    """A backed enum parameter, which is a 404 rather than a 500 when wrong."""
    import enum

    assert issubclass(annotation, enum.Enum)
    for member in annotation:
        if str(member.value) == str(value) or member.name == str(value):
            return member
    raise NotFoundHttpException(f"{value!r} is not one of {annotation.__name__}.")


async def _lookup(model: type, key: str, value: Any, *, trashed: bool) -> Any:
    query = model.query()  # type: ignore[attr-defined]
    if trashed:
        with_trashed = getattr(query, "with_trashed", None)
        if callable(with_trashed):
            query = with_trashed()
    return await _await(query.where(key, value).first())


async def _scoped_lookup(
    parent: Any,
    relationship: str,
    key: str,
    value: Any,
    *,
    trashed: bool,
) -> Any:
    """Resolve a child through its parent's relationship, or not at all."""
    relation = getattr(parent, relationship, None)
    if relation is None:
        return None
    query = relation() if callable(relation) else relation
    if trashed:
        with_trashed = getattr(query, "with_trashed", None)
        if callable(with_trashed):
            query = with_trashed()
    where = getattr(query, "where", None)
    if where is None:
        return None
    return await _await(where(key, value).first())


async def _await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def relationship_name(parameter: str) -> str:
    """The relationship a scoped binding reads on the parent.

    Laravel pluralizes the parameter: `{comment}` scoped under `{post}` looks
    for `post.comments`.
    """
    from almasix.orm.inflector import pluralize

    return pluralize(parameter)


def parent_of(
    parameter: str,
    resolved: Mapping[str, Any],
    order: list[str],
) -> Any:
    """The already-bound parameter to the left of ``parameter``, if any."""
    try:
        index = order.index(parameter)
    except ValueError:
        return None
    for earlier in reversed(order[:index]):
        found = resolved.get(earlier)
        if found is not None and not isinstance(found, (str, int, float, bool)):
            return found
    return None
