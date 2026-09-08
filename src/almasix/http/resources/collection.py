"""``ResourceCollection`` — many resources, and the paginator that carries them."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from typing import Any, ClassVar

from almasix.http.resources.resource import JsonResource


def is_paginator(candidate: Any) -> bool:
    """Duck-type a paginator so this layer need not import the ORM."""
    return all(
        hasattr(candidate, attribute) for attribute in ("items", "current_page", "per_page")
    )


class ResourceCollection(JsonResource):
    """A collection of resources.

    Declare which resource each item becomes with ``collects``; without it,
    ``UserCollection`` looks for a ``UserResource`` beside it.
    """

    #: The resource class each item is wrapped in.
    collects: ClassVar[type[JsonResource] | None] = None

    #: Keep the keys of a keyed collection instead of renumbering.
    preserve_keys: ClassVar[bool] = False

    def __init__(self, resource: Any) -> None:
        super().__init__(resource)
        self.collection = self._map_into(resource)

    # --- what this collects ---------------------------------------------

    @classmethod
    def resource_class(cls) -> type[JsonResource]:
        if cls.collects is not None:
            return cls.collects
        guessed = _guess_resource_class(cls)
        return guessed if guessed is not None else JsonResource

    def _items(self, resource: Any) -> Any:
        if is_paginator(resource):
            return resource.items
        return resource

    def _map_into(self, resource: Any) -> Any:
        items = self._items(resource)
        resource_class = type(self).resource_class()
        if self.preserve_keys and isinstance(items, Mapping):
            return {key: resource_class(item) for key, item in items.items()}
        if isinstance(items, Mapping):
            return [resource_class(item) for item in items.values()]
        return [resource_class(item) for item in items]

    # --- transformation --------------------------------------------------

    def to_dict(self, request: Any = None) -> Any:
        if isinstance(self.collection, Mapping):
            return {key: item.resolve(request) for key, item in self.collection.items()}
        return [item.resolve(request) for item in self.collection]

    def paginator(self) -> Any | None:
        """The paginator behind this collection, if there is one."""
        return self.resource if is_paginator(self.resource) else None

    def pagination_information(
        self, request: Any, paginated: Any, default: dict[str, Any]
    ) -> dict[str, Any]:
        """Override to reshape the ``meta`` / ``links`` a paginator produces."""
        del request, paginated
        return default

    # --- collection protocol ---------------------------------------------

    def __iter__(self) -> Any:
        if isinstance(self.collection, Mapping):
            return iter(self.collection.values())
        return iter(self.collection)

    def __len__(self) -> int:
        return len(self.collection)

    def count(self) -> int:
        return len(self)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} of {len(self)} items>"


class AnonymousResourceCollection(ResourceCollection):
    """What ``SomeResource.collection(...)`` returns."""

    def __init__(self, resource: Any, collects: type[JsonResource]) -> None:
        self._collects = collects
        super().__init__(resource)

    @classmethod
    def resource_class(cls) -> type[JsonResource]:  # pragma: no cover - instance wins
        return JsonResource

    def _map_into(self, resource: Any) -> Any:
        items = self._items(resource)
        if self.preserve_keys and isinstance(items, Mapping):
            return {key: self._collects(item) for key, item in items.items()}
        if isinstance(items, Mapping):
            return [self._collects(item) for item in items.values()]
        return [self._collects(item) for item in items]

    def wrapping_key(self) -> str | None:
        """Wrap the way the resource being collected wraps."""
        return self._collects.wrap


def _guess_resource_class(cls: type[ResourceCollection]) -> type[JsonResource] | None:
    """``UserCollection`` → ``UserResource``, if one lives in the same module."""
    name = cls.__name__
    if not name.endswith("Collection"):
        return None
    candidate = f"{name[: -len('Collection')]}Resource"
    module = sys.modules.get(cls.__module__)
    guessed = getattr(module, candidate, None)
    if isinstance(guessed, type) and issubclass(guessed, JsonResource):
        return guessed
    return None
