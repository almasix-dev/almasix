"""Attribute objects — Laravel's `Attribute::make(get:, set:)` accessors.

Two declaration styles are supported. As a class attribute::

    class User(Model):
        name = Attribute(get=lambda value: value.title())

Or as a method returning an ``Attribute``, which is the shape Laravel uses::

    class User(Model):
        @attribute
        def name(self) -> Attribute:
            return Attribute(get=lambda value: value.title())

Both are equivalent. The older ``get_name_attribute`` / ``set_name_attribute``
magic methods keep working — this is an addition, not a replacement.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from typing import Any

_MISSING = object()


def _arity(func: Callable[..., Any]) -> int:
    """How many positional arguments a callback will accept (capped at 2)."""
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):  # builtins without introspection
        return 2
    total = 0
    for parameter in signature.parameters.values():
        if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
            return 2
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            total += 1
    return min(total, 2)


def _call(func: Callable[..., Any], value: Any, attributes: Mapping[str, Any]) -> Any:
    """Call a get/set callback with as many arguments as it takes."""
    count = _arity(func)
    if count == 0:
        return func()
    if count == 1:
        return func(value)
    return func(value, attributes)


class Attribute:
    """A single accessor / mutator pair, Laravel's ``Attribute`` object.

    ``get`` and ``set`` may accept no arguments, just the raw value, or the
    value plus the model's raw attribute mapping.

    A ``set`` callback may return a mapping to write several columns at once,
    which is how value-object attributes are stored across multiple columns.
    Pass ``cache=True`` to compute the accessor once per instance.
    """

    def __init__(
        self,
        get: Callable[..., Any] | None = None,
        set: Callable[..., Any] | None = None,  # noqa: A002 - Laravel's argument name
        *,
        cache: bool = False,
    ) -> None:
        self.getter = get
        self.setter = set
        self.cache = cache
        self.name: str | None = None

    @classmethod
    def make(
        cls,
        get: Callable[..., Any] | None = None,
        set: Callable[..., Any] | None = None,  # noqa: A002 - Laravel's argument name
        *,
        cache: bool = False,
    ) -> Attribute:
        """Alias of the constructor, mirroring Laravel's ``Attribute::make``."""
        return cls(get=get, set=set, cache=cache)

    def with_caching(self) -> Attribute:
        """Return this attribute with accessor caching enabled."""
        self.cache = True
        return self

    # --- descriptor protocol ------------------------------------------------

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    def __get__(self, instance: Any, owner: type | None = None) -> Any:
        if instance is None:
            return self
        return instance.get_attribute(self.name)

    def __set__(self, instance: Any, value: Any) -> None:
        instance.set_attribute(self.name, value)

    # --- used by the model --------------------------------------------------

    def get_value(self, model: Any, key: str, value: Any) -> Any:
        if self.getter is None:
            return value
        if self.cache:
            cached = model._attribute_cache.get(key, _MISSING)
            if cached is not _MISSING:
                return cached
        computed = _call(self.getter, value, model.get_attributes())
        if self.cache:
            model._attribute_cache[key] = computed
        return computed

    def set_value(self, model: Any, key: str, value: Any) -> dict[str, Any]:
        """Return the raw attributes this write should produce."""
        model._attribute_cache.pop(key, None)
        if self.setter is None:
            return {key: value}
        result = _call(self.setter, value, model.get_attributes())
        if isinstance(result, Mapping):
            return dict(result)
        return {key: result}

    def has_getter(self) -> bool:
        return self.getter is not None


class MethodAttribute(Attribute):
    """An ``Attribute`` produced by a method, via the ``@attribute`` decorator."""

    def __init__(self, factory: Callable[[Any], Attribute]) -> None:
        super().__init__()
        self.factory = factory
        self.name = getattr(factory, "__name__", None)
        self.__doc__ = factory.__doc__

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    def resolve(self, model: Any) -> Attribute:
        resolved = self.factory(model)
        if not isinstance(resolved, Attribute):
            raise TypeError(
                f"{type(model).__name__}.{self.name}() must return an Attribute, "
                f"got {type(resolved).__name__}"
            )
        resolved.name = self.name
        return resolved

    def get_value(self, model: Any, key: str, value: Any) -> Any:
        return self.resolve(model).get_value(model, key, value)

    def set_value(self, model: Any, key: str, value: Any) -> dict[str, Any]:
        return self.resolve(model).set_value(model, key, value)

    def has_getter(self) -> bool:
        return True


def attribute(func: Callable[[Any], Attribute]) -> MethodAttribute:
    """Declare an accessor from a method that returns an :class:`Attribute`."""
    return MethodAttribute(func)
