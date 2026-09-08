"""Laravel-shaped ``Arr`` helpers."""

from __future__ import annotations

import random
from collections.abc import (
    Callable,
    Iterable,
    Mapping,
    MutableMapping,
    MutableSequence,
    Sequence,
)
from typing import Any
from urllib.parse import urlencode

from avalon.support.collection import data_get


class Arr:
    """Static array helpers (Laravel ``Illuminate\\Support\\Arr``)."""

    @staticmethod
    def accessible(value: Any) -> bool:
        return isinstance(value, (Mapping, Sequence)) and not isinstance(value, (str, bytes))

    @staticmethod
    def add(array: MutableMapping[Any, Any], key: str, value: Any) -> MutableMapping[Any, Any]:
        if data_get(array, key) is None:
            Arr.set(array, key, value)
        return array

    @staticmethod
    def collapse(array: Iterable[Any]) -> list[Any]:
        results: list[Any] = []
        for item in array:
            if isinstance(item, Mapping):
                results.extend(item.values())
            elif isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
                results.extend(item)
            else:
                results.append(item)
        return results

    @staticmethod
    def cross_join(*arrays: Iterable[Any]) -> list[list[Any]]:
        pools = [list(a) for a in arrays]
        if not pools:
            return [[]]
        result: list[list[Any]] = [[]]
        for pool in pools:
            result = [prefix + [item] for prefix in result for item in pool]
        return result

    @staticmethod
    def divide(array: Mapping[Any, Any]) -> tuple[list[Any], list[Any]]:
        return list(array.keys()), list(array.values())

    @staticmethod
    def dot(array: Mapping[Any, Any] | Sequence[Any], prepend: str = "") -> dict[str, Any]:
        results: dict[str, Any] = {}

        def walk(value: Any, prefix: str) -> None:
            if isinstance(value, Mapping):
                if not value and prefix:
                    results[prefix[:-1] if prefix.endswith(".") else prefix] = {}
                    return
                for key, item in value.items():
                    walk(item, f"{prefix}{key}.")
            elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                if not value and prefix:
                    results[prefix[:-1]] = []
                    return
                for index, item in enumerate(value):
                    walk(item, f"{prefix}{index}.")
            else:
                results[prefix[:-1]] = value

        walk(array, prepend)
        return results

    @staticmethod
    def undot(array: Mapping[str, Any]) -> dict[Any, Any]:
        results: dict[Any, Any] = {}
        for key, value in array.items():
            Arr.set(results, key, value)
        return results

    @staticmethod
    def except_(array: Mapping[Any, Any], keys: str | Iterable[str]) -> dict[Any, Any]:
        key_list = [keys] if isinstance(keys, str) else list(keys)
        return {k: v for k, v in array.items() if k not in key_list}

    @staticmethod
    def only(array: Mapping[Any, Any], keys: str | Iterable[str]) -> dict[Any, Any]:
        key_list = [keys] if isinstance(keys, str) else list(keys)
        return {k: array[k] for k in key_list if k in array}

    @staticmethod
    def exists(array: Mapping[Any, Any] | Sequence[Any], key: Any) -> bool:
        if isinstance(array, Mapping):
            return key in array
        if isinstance(array, Sequence) and not isinstance(array, (str, bytes)):
            try:
                return 0 <= int(key) < len(array)
            except (TypeError, ValueError):
                return False
        return False

    @staticmethod
    def first(
        array: Iterable[Any],
        callback: Callable[[Any], bool] | None = None,
        default: Any = None,
    ) -> Any:
        for item in array:
            if callback is None or callback(item):
                return item
        return default() if callable(default) else default

    @staticmethod
    def last(
        array: Sequence[Any] | Iterable[Any],
        callback: Callable[[Any], bool] | None = None,
        default: Any = None,
    ) -> Any:
        items = list(array)
        if callback is None:
            return items[-1] if items else (default() if callable(default) else default)
        for item in reversed(items):
            if callback(item):
                return item
        return default() if callable(default) else default

    @staticmethod
    def flatten(array: Iterable[Any], depth: float = float("inf")) -> list[Any]:
        results: list[Any] = []

        def walk(items: Iterable[Any], level: float) -> None:
            iterable: Iterable[Any]
            if isinstance(items, Mapping):
                iterable = items.values()
            else:
                iterable = items
            for item in iterable:
                if (
                    isinstance(item, Sequence)
                    and not isinstance(item, (str, bytes))
                    and level > 0
                ):
                    walk(item, level - 1)
                elif isinstance(item, Mapping) and level > 0:
                    walk(item, level - 1)  # pragma: no branch
                else:
                    results.append(item)

        walk(array, depth)
        return results

    @staticmethod
    def forget(array: MutableMapping[Any, Any], keys: str | Iterable[str]) -> None:
        key_list = [keys] if isinstance(keys, str) else list(keys)
        for key in key_list:
            segments = str(key).split(".")
            current: Any = array
            for segment in segments[:-1]:
                if not isinstance(current, MutableMapping) or segment not in current:
                    break
                current = current[segment]
            else:
                if isinstance(current, MutableMapping):
                    current.pop(segments[-1], None)

    @staticmethod
    def get(array: Any, key: str | None, default: Any = None) -> Any:
        return data_get(array, key, default)

    @staticmethod
    def has(array: Any, keys: str | Iterable[str]) -> bool:
        key_list = [keys] if isinstance(keys, str) else list(keys)
        if not key_list:
            return False
        return all(_has_path(array, str(key)) for key in key_list)

    @staticmethod
    def has_any(array: Any, keys: str | Iterable[str]) -> bool:
        key_list = [keys] if isinstance(keys, str) else list(keys)
        return any(_has_path(array, str(key)) for key in key_list)

    @staticmethod
    def is_assoc(array: Mapping[Any, Any] | Sequence[Any]) -> bool:
        if isinstance(array, Mapping):
            keys = list(array.keys())
            return keys != list(range(len(keys)))
        return False

    @staticmethod
    def is_list(array: Any) -> bool:
        if isinstance(array, list):
            return True
        if isinstance(array, Mapping):
            keys = list(array.keys())
            return keys == list(range(len(keys)))
        return False

    @staticmethod
    def join(array: Iterable[Any], glue: str, final_glue: str = "") -> str:
        items = [str(item) for item in array]
        if not items:
            return ""
        if final_glue and len(items) > 1:
            return glue.join(items[:-1]) + final_glue + items[-1]
        return glue.join(items)

    @staticmethod
    def key_by(array: Iterable[Any], key_by: str | Callable[[Any], Any]) -> dict[Any, Any]:
        results: dict[Any, Any] = {}
        for item in array:
            key = key_by(item) if callable(key_by) else data_get(item, key_by)
            results[key] = item
        return results

    @staticmethod
    def map(array: Mapping[Any, Any] | Sequence[Any], callback: Callable[..., Any]) -> list[Any]:
        if isinstance(array, Mapping):
            return [callback(value, key) for key, value in array.items()]
        return [callback(value, index) for index, value in enumerate(array)]

    @staticmethod
    def map_with_keys(
        array: Mapping[Any, Any] | Sequence[Any],
        callback: Callable[..., Mapping[Any, Any] | tuple[Any, Any]],
    ) -> dict[Any, Any]:
        results: dict[Any, Any] = {}
        iterable: Iterable[tuple[Any, Any]]
        if isinstance(array, Mapping):
            iterable = array.items()
        else:
            iterable = enumerate(array)
        for key, value in iterable:
            mapped = callback(value, key)
            if isinstance(mapped, Mapping):
                results.update(mapped)
            else:
                mk, mv = mapped
                results[mk] = mv
        return results

    @staticmethod
    def map_spread(array: Iterable[Any], callback: Callable[..., Any]) -> list[Any]:
        results: list[Any] = []
        for item in array:
            if isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
                results.append(callback(*item))
            else:
                results.append(callback(item))
        return results

    @staticmethod
    def pluck(
        array: Iterable[Any],
        value: str | Callable[[Any], Any],
        key: str | Callable[[Any], Any] | None = None,
    ) -> list[Any] | dict[Any, Any]:
        if key is None:
            return [
                value(item) if callable(value) else data_get(item, value) for item in array
            ]
        results: dict[Any, Any] = {}
        for item in array:
            item_key = key(item) if callable(key) else data_get(item, key)
            results[item_key] = value(item) if callable(value) else data_get(item, value)
        return results

    @staticmethod
    def prepend(array: list[Any], value: Any, key: Any | None = None) -> list[Any] | dict[Any, Any]:
        if key is None:
            return [value, *array]
        result: dict[Any, Any] = {key: value}
        if isinstance(array, Mapping):
            result.update(array)
        else:
            result.update(enumerate(array))
        return result

    @staticmethod
    def prepend_keys_with(array: Mapping[Any, Any], prepend_with: str) -> dict[str, Any]:
        return {f"{prepend_with}{key}": value for key, value in array.items()}

    @staticmethod
    def pull(
        array: MutableMapping[Any, Any],
        key: str,
        default: Any = None,
    ) -> Any:
        value = data_get(array, key, default)
        Arr.forget(array, key)
        return value

    @staticmethod
    def query(array: Mapping[str, Any]) -> str:
        return urlencode(array, doseq=True)

    @staticmethod
    def random(array: Sequence[Any], number: int | None = None) -> Any:
        if number is None:
            return random.choice(list(array))
        return random.sample(list(array), k=min(number, len(list(array))))

    @staticmethod
    def reject(array: Iterable[Any], callback: Callable[[Any], bool]) -> list[Any]:
        return [item for item in array if not callback(item)]

    @staticmethod
    def set(array: MutableMapping[Any, Any], key: str, value: Any) -> MutableMapping[Any, Any]:
        segments = str(key).split(".")
        current: Any = array
        for segment in segments[:-1]:
            existing = _child(current, segment)
            if not isinstance(existing, (MutableMapping, MutableSequence)):
                existing = {}
                _put(current, segment, existing)
            current = existing
        _put(current, segments[-1], value)
        return array

    @staticmethod
    def shuffle(array: Sequence[Any]) -> list[Any]:
        items = list(array)
        random.shuffle(items)
        return items

    @staticmethod
    def sort(
        array: Mapping[Any, Any] | Sequence[Any],
        callback: Callable[[Any], Any] | None = None,
    ) -> dict[Any, Any] | list[Any]:
        if isinstance(array, Mapping):
            items = list(array.items())
            if callback is None:
                items.sort(key=lambda pair: pair[1])
            else:
                items.sort(key=lambda pair: callback(pair[1]))
            return dict(items)
        items_list = list(array)
        if callback is None:
            return sorted(items_list)
        return sorted(items_list, key=callback)

    @staticmethod
    def sort_desc(
        array: Mapping[Any, Any] | Sequence[Any],
        callback: Callable[[Any], Any] | None = None,
    ) -> dict[Any, Any] | list[Any]:
        sorted_items = Arr.sort(array, callback)
        if isinstance(sorted_items, dict):
            return dict(reversed(list(sorted_items.items())))
        return list(reversed(sorted_items))

    @staticmethod
    def sort_recursive(array: Any, descending: bool = False) -> Any:
        if isinstance(array, Mapping):
            items = {
                key: Arr.sort_recursive(value, descending=descending)
                for key, value in array.items()
            }
            return dict(sorted(items.items(), reverse=descending))
        if isinstance(array, Sequence) and not isinstance(array, (str, bytes)):
            items_list = [Arr.sort_recursive(value, descending=descending) for value in array]
            try:
                return sorted(items_list, reverse=descending)
            except TypeError:  # pragma: no cover
                return items_list
        return array

    @staticmethod
    def take(array: Sequence[Any], limit: int) -> list[Any]:
        items = list(array)
        if limit < 0:
            return items[limit:]
        return items[:limit]

    @staticmethod
    def to_css_classes(array: Mapping[str, Any] | Sequence[Any]) -> str:
        if isinstance(array, Mapping):
            return " ".join(key for key, enabled in array.items() if enabled)
        return " ".join(str(item) for item in array if item)

    @staticmethod
    def to_css_styles(array: Mapping[str, Any] | Sequence[Any]) -> str:
        """Build a ``style`` attribute from properties, or from switched styles."""
        parts = []
        pairs = array.items() if isinstance(array, Mapping) else [(item, True) for item in array]
        for key, value in pairs:
            if value is False or value is None:
                continue
            # ``{"color": "red"}`` is a property and its value; ``{"color: red": True}``
            # is a whole style switched on by a flag, which is Laravel's shape.
            parts.append(str(key) if value is True else f"{key}:{value}")
        return ";".join(part.rstrip(";") for part in parts)

    @staticmethod
    def where(array: Iterable[Any], callback: Callable[[Any], bool]) -> list[Any]:
        return [item for item in array if callback(item)]

    @staticmethod
    def where_not_null(array: Iterable[Any]) -> list[Any]:
        return [item for item in array if item is not None]

    @staticmethod
    def wrap(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return list(value)
        return [value]


def _child(container: Any, segment: str) -> Any:
    """Read one segment, whether the container is keyed or indexed."""
    if isinstance(container, MutableSequence):
        try:
            return container[int(segment)]
        except (ValueError, IndexError):
            return None
    return container.get(segment)


def _put(container: Any, segment: str, value: Any) -> None:
    """Write one segment, growing a list when the segment is its next index."""
    if isinstance(container, MutableSequence):
        try:
            index = int(segment)
        except ValueError:
            raise TypeError(f"Cannot use {segment!r} as an index into a list.") from None
        while len(container) <= index:
            container.append(None)
        container[index] = value
        return
    container[segment] = value


def _has_path(target: Any, key: str) -> bool:
    current = target
    for segment in key.split("."):
        if isinstance(current, Mapping):
            if segment not in current:
                return False
            current = current[segment]
        elif isinstance(current, Sequence) and not isinstance(current, (str, bytes)):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError):
                return False
        elif hasattr(current, segment):
            current = getattr(current, segment)
        else:
            return False
    return True


# Snake aliases matching Python style call sites.
Arr.except_keys = Arr.except_  # type: ignore[attr-defined]
Arr.crossJoin = Arr.cross_join  # type: ignore[attr-defined]
Arr.hasAny = Arr.has_any  # type: ignore[attr-defined]
Arr.isAssoc = Arr.is_assoc  # type: ignore[attr-defined]
Arr.isList = Arr.is_list  # type: ignore[attr-defined]
Arr.keyBy = Arr.key_by  # type: ignore[attr-defined]
Arr.mapSpread = Arr.map_spread  # type: ignore[attr-defined]
Arr.mapWithKeys = Arr.map_with_keys  # type: ignore[attr-defined]
def _typed(array: Any, key: str | None, expected: type | tuple[type, ...], label: str) -> Any:
    """``Arr.get`` with a type assertion, for reading configuration safely."""
    value = data_get(array, key)
    if not isinstance(value, expected) or isinstance(value, bool) is not (expected is bool):
        raise TypeError(f"Value for {key!r} is not {label}: {value!r}")
    return value


class _ArrExtras:
    """Methods installed onto :class:`Arr`; grouped here only for readability."""

    @staticmethod
    def array(array: Any, key: str | None = None) -> list[Any]:
        """Read a value, insisting it is a list."""
        return _typed(array, key, list, "a list")

    @staticmethod
    def boolean(array: Any, key: str | None = None) -> bool:
        """Read a value, insisting it is a boolean."""
        return _typed(array, key, bool, "a boolean")

    @staticmethod
    def integer(array: Any, key: str | None = None) -> int:
        """Read a value, insisting it is an integer."""
        return _typed(array, key, int, "an integer")

    @staticmethod
    def float(array: Any, key: str | None = None) -> float:
        """Read a value, insisting it is a float."""
        return _typed(array, key, float, "a float")

    @staticmethod
    def string(array: Any, key: str | None = None) -> str:
        """Read a value, insisting it is a string."""
        return _typed(array, key, str, "a string")

    @staticmethod
    def from_(value: Any) -> Any:
        """Convert whatever it is given into a plain list or dict.

        Laravel spells this ``Arr::from``; ``from`` is a keyword in Python.
        """
        if value is None:
            return []
        if isinstance(value, Mapping):
            return dict(value)
        for method in ("to_dict", "to_array", "all"):
            converter = getattr(value, method, None)
            if callable(converter):
                return Arr.from_(converter())
        if isinstance(value, (str, bytes)):
            return [value]
        if hasattr(value, "__dict__") and not isinstance(value, Iterable):
            return dict(vars(value))
        if isinstance(value, Iterable):
            return list(value)
        return [value]  # pragma: no cover - non-iterable scalars

    @staticmethod
    def has_all(array: Any, keys: str | Iterable[str]) -> bool:
        """Whether every one of the keys exists, in dot notation."""
        key_list = [keys] if isinstance(keys, str) else list(keys)
        return bool(key_list) and all(Arr.has(array, key) for key in key_list)

    @staticmethod
    def every(array: Iterable[Any], callback: Callable[[Any], bool]) -> bool:
        """Whether the callback holds for every item."""
        return all(callback(item) for item in array)

    @staticmethod
    def some(array: Iterable[Any], callback: Callable[[Any], bool]) -> bool:
        """Whether the callback holds for at least one item."""
        return any(callback(item) for item in array)

    @staticmethod
    def sole(array: Iterable[Any], callback: Callable[[Any], bool] | None = None) -> Any:
        """The one matching item, raising if there are none or several."""
        from avalon.support.collection import ItemNotFoundError, MultipleItemsFoundError

        matches = [item for item in array if callback is None or callback(item)]
        if not matches:
            raise ItemNotFoundError("No matching item found.")
        if len(matches) > 1:
            raise MultipleItemsFoundError(f"{len(matches)} items were found.")
        return matches[0]

    @staticmethod
    def partition(
        array: Iterable[Any], callback: Callable[[Any], bool]
    ) -> tuple[list[Any], list[Any]]:
        """Split into the items that pass and the items that do not."""
        passed: list[Any] = []
        failed: list[Any] = []
        for item in array:
            (passed if callback(item) else failed).append(item)
        return passed, failed

    @staticmethod
    def push(array: MutableMapping[Any, Any], key: str, *values: Any) -> MutableMapping[Any, Any]:
        """Append to the list at a dot-notation key, creating it if needed."""
        current = data_get(array, key)
        if current is None:
            current = []
            Arr.set(array, key, current)
        current.extend(values)
        return array

    @staticmethod
    def select(array: Iterable[Any], keys: str | Iterable[str]) -> list[dict[Any, Any]]:
        """Keep only the given keys from each row."""
        key_list = [keys] if isinstance(keys, str) else list(keys)
        return [Arr.only(item, key_list) for item in array]

    @staticmethod
    def only_values(array: Iterable[Any], values: Iterable[Any]) -> list[Any]:
        """Keep only the given values."""
        wanted = list(values)
        return [item for item in array if item in wanted]

    @staticmethod
    def except_values(array: Iterable[Any], values: Iterable[Any]) -> list[Any]:
        """Remove the given values."""
        unwanted = list(values)
        return [item for item in array if item not in unwanted]


for _name, _member in vars(_ArrExtras).items():
    if isinstance(_member, staticmethod):
        setattr(Arr, _name, _member)
Arr.hasAll = Arr.has_all  # type: ignore[attr-defined]
Arr.onlyValues = Arr.only_values  # type: ignore[attr-defined]
Arr.exceptValues = Arr.except_values  # type: ignore[attr-defined]
setattr(Arr, "from", Arr.from_)

Arr.prependKeysWith = Arr.prepend_keys_with  # type: ignore[attr-defined]
Arr.sortDesc = Arr.sort_desc  # type: ignore[attr-defined]
Arr.sortRecursive = Arr.sort_recursive  # type: ignore[attr-defined]
Arr.toCssClasses = Arr.to_css_classes  # type: ignore[attr-defined]
Arr.toCssStyles = Arr.to_css_styles  # type: ignore[attr-defined]
Arr.whereNotNull = Arr.where_not_null  # type: ignore[attr-defined]
