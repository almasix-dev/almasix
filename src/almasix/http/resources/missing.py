"""Missing and merged values — the sentinels conditional attributes return."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Self


class PotentiallyMissing:
    """Marker for values that may vanish from a resource's output."""

    def is_missing(self) -> bool:  # pragma: no cover - abstract
        raise NotImplementedError


class MissingValue(PotentiallyMissing):
    """A value that should be dropped from the resource entirely."""

    _instance: MissingValue | None = None

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def is_missing(self) -> bool:
        return True

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "<missing>"


#: The single missing marker — compare with ``is`` or call ``MissingValue()``.
MISSING = MissingValue()


class Resolvable:
    """Something that filters itself — in practice, a nested resource."""

    def resolve(self, request: Any = None) -> Any:  # pragma: no cover - abstract
        raise NotImplementedError


class MergeValue:
    """Values that merge into the parent instead of nesting under a key."""

    def __init__(self, data: Any) -> None:
        self.data = data

    def items(self) -> list[tuple[Any, Any]]:
        """Pairs to splice in: mappings keep their keys, sequences renumber."""
        if isinstance(self.data, Mapping):
            return list(self.data.items())
        if isinstance(self.data, Sequence) and not isinstance(self.data, (str, bytes)):
            return [(index, value) for index, value in enumerate(self.data)]
        return [(0, self.data)]


class MissingMergeValue(MergeValue, PotentiallyMissing):
    """A merge that did not happen, because its condition was false."""

    def __init__(self) -> None:
        super().__init__({})

    def is_missing(self) -> bool:
        return True


def is_missing(value: Any) -> bool:
    return isinstance(value, PotentiallyMissing) and value.is_missing()


def filter_data(data: Any, request: Any = None) -> Any:
    """Drop missing values, splice merges, and resolve nested resources.

    Laravel filters recursively so a `when()` buried in a nested array still
    disappears cleanly, and a `merge_when()` flattens into its parent. A
    nested resource is resolved here rather than at render time, so its own
    conditional attributes are filtered too.
    """
    if isinstance(data, Resolvable):
        return data.resolve(request)
    if isinstance(data, Mapping):
        return _filter_mapping(data, request)
    if isinstance(data, (list, tuple)):
        return _filter_sequence(data, request)
    return data


def _filter_mapping(data: Mapping[Any, Any], request: Any) -> dict[Any, Any]:
    filtered: dict[Any, Any] = {}
    index = 0
    for key, value in data.items():
        if is_missing(value):
            continue
        if isinstance(value, MergeValue):
            for merge_key, merge_value in value.items():
                if is_missing(merge_value):
                    continue
                if isinstance(merge_key, int):
                    filtered[index] = filter_data(merge_value, request)
                    index += 1
                else:
                    filtered[merge_key] = filter_data(merge_value, request)
            continue
        filtered[key] = filter_data(value, request)
    return filtered


def _filter_sequence(data: Sequence[Any], request: Any) -> list[Any]:
    filtered: list[Any] = []
    for value in data:
        if is_missing(value):
            continue
        if isinstance(value, MergeValue):
            filtered.extend(
                filter_data(merge_value, request)
                for _key, merge_value in value.items()
                if not is_missing(merge_value)
            )
            continue
        filtered.append(filter_data(value, request))
    return filtered
