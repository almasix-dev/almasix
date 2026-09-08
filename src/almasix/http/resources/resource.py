"""``JsonResource`` — the transformation layer between models and JSON."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any, ClassVar

from almasix.http.resources.missing import (
    MISSING,
    MergeValue,
    MissingMergeValue,
    Resolvable,
    filter_data,
)
from almasix.support.arity import accepts_two_arguments

#: Sentinel meaning "the caller did not pass this argument at all", which is
#: different from passing the missing marker on purpose.
_UNSET = object()


class JsonResource(Resolvable):
    """Transforms one thing — usually a model — into a JSON-ready dict.

    Subclass it and override :meth:`to_dict`. Attributes not defined on the
    resource fall through to the underlying object, so ``self.id`` reads the
    model's ``id``.
    """

    #: Key the outermost resource is wrapped in; ``None`` disables wrapping.
    wrap: ClassVar[str | None] = "data"

    def __init__(self, resource: Any) -> None:
        self.resource = resource
        self._additional: dict[str, Any] = {}
        self._status = 200
        self._headers: dict[str, str] = {}

    # --- construction ---------------------------------------------------

    @classmethod
    def make(cls, *args: Any, **kwargs: Any) -> JsonResource:
        return cls(*args, **kwargs)

    @classmethod
    def collection(cls, resource: Any) -> Any:
        """Wrap many of these (Laravel ``UserResource::collection($users)``)."""
        from almasix.http.resources.collection import AnonymousResourceCollection

        return AnonymousResourceCollection(resource, cls)

    # --- wrapping -------------------------------------------------------

    @classmethod
    def without_wrapping(cls) -> None:
        """Stop wrapping the outermost resource in a ``data`` key."""
        cls.wrap = None

    @classmethod
    def wrap_with(cls, key: str | None) -> None:
        cls.wrap = key

    def wrapping_key(self) -> str | None:
        """The key this instance's data is wrapped in, if any."""
        return type(self).wrap

    # --- the transformation ---------------------------------------------

    def to_dict(self, request: Any = None) -> Any:
        """Override this. The default serializes whatever it was given."""
        del request
        return _default_shape(self.resource)

    def with_(self, request: Any = None) -> dict[str, Any]:
        """Extra top-level data for every response of this resource."""
        del request
        return {}

    def additional(self, data: Mapping[str, Any]) -> JsonResource:
        """Extra top-level data for *this* response only."""
        self._additional.update(dict(data))
        return self

    def resolve(self, request: Any = None) -> Any:
        """The filtered data, without any wrapping."""
        data = self.to_dict(request)
        if hasattr(data, "to_dict") and not isinstance(data, (dict, list)):
            data = data.to_dict()
        return filter_data(data, request)

    # --- responses ------------------------------------------------------

    def status(self, code: int) -> JsonResource:
        self._status = code
        return self

    def header(self, name: str, value: str) -> JsonResource:
        self._headers[name] = value
        return self

    def headers(self, headers: Mapping[str, str]) -> JsonResource:
        self._headers.update({str(k): str(v) for k, v in headers.items()})
        return self

    def with_response(self, request: Any, response: Any) -> None:
        """Hook for tweaking the response this resource produced."""

    def response(self, request: Any = None) -> Any:
        from almasix.http.resources.response import ResourceResponse

        return ResourceResponse(self).to_response(request)

    def to_response(self) -> Any:
        """Makes a resource returnable straight from a controller."""
        return self.response()

    # --- conditional attributes -----------------------------------------

    def when(self, condition: Any, value: Any = MISSING, default: Any = MISSING) -> Any:
        """Include ``value`` only when ``condition`` holds."""
        if callable(condition):
            condition = condition()
        if condition:
            return value() if callable(value) else value
        return default() if callable(default) else default

    def unless(self, condition: Any, value: Any = MISSING, default: Any = MISSING) -> Any:
        if callable(condition):
            condition = condition()
        return self.when(not condition, value, default)

    def merge_when(self, condition: Any, values: Any = MISSING) -> MergeValue:
        """Merge ``values`` into the parent when ``condition`` holds."""
        if callable(condition):
            condition = condition()
        if not condition:
            return MissingMergeValue()
        return MergeValue(values() if callable(values) else values)

    def merge_unless(self, condition: Any, values: Any = MISSING) -> MergeValue:
        if callable(condition):
            condition = condition()
        return self.merge_when(not condition, values)

    def merge(self, values: Any) -> MergeValue:
        return MergeValue(values() if callable(values) else values)

    def when_has(self, attribute: str, value: Any = _UNSET, default: Any = MISSING) -> Any:
        """Include an attribute only when the underlying object has one."""
        if not _has_attribute(self.resource, attribute):
            return default() if callable(default) else default
        if value is _UNSET:
            return _read_attribute(self.resource, attribute)
        return value() if callable(value) else value

    def when_not_null(self, value: Any, default: Any = MISSING) -> Any:
        resolved = value() if callable(value) else value
        if resolved is None:
            return default() if callable(default) else default
        return resolved

    def when_loaded(self, relationship: str, value: Any = _UNSET, default: Any = MISSING) -> Any:
        """Include a relationship only when it was eager loaded."""
        loader = getattr(self.resource, "relation_loaded", None)
        if not callable(loader) or not loader(relationship):
            return default() if callable(default) else default
        loaded = self.resource.get_relations()[relationship]
        if value is _UNSET:
            return loaded
        return value(loaded) if _takes_argument(value) else (value() if callable(value) else value)

    def when_counted(self, relationship: str, value: Any = _UNSET, default: Any = MISSING) -> Any:
        """Include a ``with_count`` result only when it was loaded."""
        return self._when_extra(f"{relationship}_count", value, default)

    def when_aggregated(
        self,
        relationship: str,
        column: str,
        aggregate: str,
        value: Any = _UNSET,
        default: Any = MISSING,
    ) -> Any:
        """Include a ``with_sum`` / ``with_avg`` / … result when it was loaded."""
        return self._when_extra(f"{relationship}_{aggregate}_{column}", value, default)

    def when_pivot_loaded(
        self, table: str, value: Any = MISSING, default: Any = MISSING
    ) -> Any:
        return self.when_pivot_loaded_as("pivot", table, value, default)

    def when_pivot_loaded_as(
        self, accessor: str, table: str, value: Any = MISSING, default: Any = MISSING
    ) -> Any:
        """Include pivot data only when the intermediate row is present."""
        loader = getattr(self.resource, "relation_loaded", None)
        if not callable(loader) or not loader(accessor):
            return default() if callable(default) else default
        pivot = self.resource.get_relations()[accessor]
        if _pivot_table(pivot) != table:
            return default() if callable(default) else default
        return value(pivot) if _takes_argument(value) else (value() if callable(value) else value)

    def when_appended(self, attribute: str, value: Any = _UNSET, default: Any = MISSING) -> Any:
        """Include an appended accessor only when the model appends it."""
        appends = getattr(self.resource, "get_appends", None)
        if not callable(appends) or attribute not in appends():
            return default() if callable(default) else default
        if value is _UNSET:
            return _read_attribute(self.resource, attribute)
        return value() if callable(value) else value

    def _when_extra(self, key: str, value: Any, default: Any) -> Any:
        extra = getattr(self.resource, "_extra", None)
        if not isinstance(extra, dict) or key not in extra:
            return default() if callable(default) else default
        if value is _UNSET:
            return extra[key]
        return value() if callable(value) else value

    # --- proxying -------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        # Only reached for names the resource itself does not define, which
        # is what makes ``self.id`` read the underlying model.
        if name.startswith("__") or name == "resource":
            raise AttributeError(name)
        try:
            resource = object.__getattribute__(self, "resource")
        except AttributeError:  # pragma: no cover - during __init__
            raise AttributeError(name) from None
        try:
            return getattr(resource, name)
        except AttributeError:
            if isinstance(resource, Mapping) and name in resource:
                return resource[name]
            raise

    def __getitem__(self, key: Any) -> Any:
        if isinstance(self.resource, Mapping):
            return self.resource[key]
        return getattr(self.resource, key)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} of {self.resource!r}>"


def _default_shape(resource: Any) -> Any:
    """What a resource returns when ``to_dict`` was not overridden."""
    if resource is None:
        return {}
    serializer = getattr(resource, "to_dict", None)
    if callable(serializer):
        return serializer()
    if isinstance(resource, Mapping):
        return dict(resource)
    return resource


def _has_attribute(resource: Any, attribute: str) -> bool:
    if isinstance(resource, Mapping):
        return attribute in resource
    attributes = getattr(resource, "get_attributes", None)
    if callable(attributes):
        return attribute in attributes()
    return hasattr(resource, attribute)


def _read_attribute(resource: Any, attribute: str) -> Any:
    if isinstance(resource, Mapping):
        return resource[attribute]
    return getattr(resource, attribute)


def _pivot_table(pivot: Any) -> str | None:
    """A ``Pivot`` knows the intermediate table it came from; anything else guesses."""
    named = getattr(pivot, "get_pivot_table", None)
    if callable(named):
        return str(named())
    return getattr(pivot, "table", None)


def _takes_argument(value: Any) -> bool:
    """True for callables that want the loaded relation or pivot passed in."""
    if not callable(value):
        return False
    try:
        parameters = inspect.signature(value).parameters
    except (TypeError, ValueError):  # pragma: no cover - builtins
        return False
    if accepts_two_arguments(value):
        return True
    return any(
        p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.VAR_POSITIONAL)
        for p in parameters.values()
    )
