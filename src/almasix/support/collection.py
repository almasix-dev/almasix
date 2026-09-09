"""Laravel-shaped Support ``Collection`` — fluent list/map helpers."""

from __future__ import annotations

import json
import random
import statistics
from collections import Counter, OrderedDict
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from itertools import product
from typing import Any, Generic, Self, TypeVar

T = TypeVar("T")
_macros: dict[str, Callable[..., Any]] = {}


def data_get(target: Any, key: str | None, default: Any = None) -> Any:
    """Dot-notation get, including ``*`` wildcards (Laravel ``data_get``)."""
    if key is None:
        return target
    segments = str(key).split(".")
    if "*" in segments:
        return _data_get_wildcard(target, segments, default)
    current = target
    for segment in segments:
        if current is None:
            return default
        if isinstance(current, Mapping):
            if segment not in current:
                return default
            current = current[segment]
        elif isinstance(current, Sequence) and not isinstance(current, (str, bytes)):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError):
                return default
        else:
            getter = getattr(current, "get_attribute", None)
            if callable(getter):
                current = getter(segment)
            elif hasattr(current, segment):
                current = getattr(current, segment)
            else:
                return default
    return current


def _data_get_wildcard(target: Any, segments: list[str], default: Any) -> Any:
    """Collect every branch a ``*`` segment fans out to."""
    star = segments.index("*")
    before, after = segments[:star], segments[star + 1 :]
    branch = data_get(target, ".".join(before), None) if before else target
    if isinstance(branch, Mapping):
        items: Any = list(branch.values())
    elif isinstance(branch, Sequence) and not isinstance(branch, (str, bytes)):
        items = list(branch)
    else:
        return default
    if not after:
        return items
    collected = [data_get(item, ".".join(after), None) for item in items]
    collected = [item for item in collected if item is not None]
    if "*" not in after:
        return collected
    # A second wildcard collapses one level, as Laravel's does; every branch
    # reached past a wildcard is itself a list.
    return [inner for branch_items in collected for inner in branch_items]


def value_get(item: Any, key: str | Callable[[Any], Any] | None) -> Any:
    if key is None:
        return item
    if callable(key):
        return key(item)
    return data_get(item, str(key))


def _as_items(items: Any) -> OrderedDict[Any, Any]:
    if items is None:
        return OrderedDict()
    if isinstance(items, Collection):
        return OrderedDict(items._items)
    if isinstance(items, Mapping):
        return OrderedDict(items)
    if isinstance(items, (str, bytes)):
        return OrderedDict([(0, items)])
    return OrderedDict(enumerate(list(items)))


class Collection(Generic[T]):
    """Fluent Support collection (Laravel ``Illuminate\\Support\\Collection``)."""

    __slots__ = ("_items",)

    def __init__(self, items: Any = None) -> None:
        self._items: OrderedDict[Any, Any] = _as_items(items)

    # --- construction -------------------------------------------------------

    @classmethod
    def make(cls, items: Any = None) -> Self:
        return cls(items)

    @classmethod
    def wrap(cls, value: Any) -> Self:
        if isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            return cls(value)
        if value is None:
            return cls()
        return cls([value] if not isinstance(value, (list, tuple, set)) else value)

    @classmethod
    def unwrap(cls, value: Any) -> Any:
        return value.all() if isinstance(value, Collection) else value

    @classmethod
    def times(cls, count: int, callback: Callable[[int], Any] | None = None) -> Self:
        if callback is None:
            return cls(range(1, count + 1))
        return cls(callback(index) for index in range(1, count + 1))

    @classmethod
    def range(cls, start: int, end: int) -> Self:
        step = 1 if end >= start else -1
        return cls(range(start, end + step, step))

    @classmethod
    def macro(cls, name: str, callback: Callable[..., Any]) -> None:
        _macros[name] = callback

    def __getattr__(self, name: str) -> Any:
        if name in _macros:
            macro = _macros[name]

            def invoker(*args: Any, **kwargs: Any) -> Any:
                return macro(self, *args, **kwargs)

            return invoker
        raise AttributeError(name)

    def _new(self, items: Any) -> Self:
        return type(self)(items)

    def _list_like(self) -> bool:
        keys = list(self._items.keys())
        return keys == list(range(len(keys)))

    def _values_list(self) -> list[Any]:
        return list(self._items.values())

    # --- container ----------------------------------------------------------

    def _reindex_list_keys(self) -> None:
        if self._items and all(isinstance(key, int) for key in self._items):
            self._items = OrderedDict(enumerate(self._values_list()))

    def __iter__(self) -> Iterator[Any]:
        return iter(self._items.values())

    def __len__(self) -> int:
        return len(self._items)

    def __bool__(self) -> bool:
        return bool(self._items)

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, slice):
            values = self._values_list()[key]
            return self._new(values)
        if key in self._items:
            return self._items[key]
        if isinstance(key, int) and self._list_like():
            try:
                return self._values_list()[key]
            except IndexError as exc:
                raise KeyError(key) from exc
        raise KeyError(key)

    def __setitem__(self, key: Any, value: Any) -> None:
        self._items[key] = value

    def __contains__(self, item: Any) -> bool:
        return item in self._items.values()

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Collection):
            return self._values_list() == other._values_list() and list(self._items.keys()) == list(
                other._items.keys()
            )
        if isinstance(other, list):
            return self._values_list() == other
        if isinstance(other, Mapping):
            return dict(self._items) == dict(other)
        return NotImplemented

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.all()!r})"

    # --- access -------------------------------------------------------------

    def all(self) -> Any:
        if self._list_like():
            return self._values_list()
        return dict(self._items)

    def to_array(self) -> Any:
        return self.all()

    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self.to_array(), default=str, **kwargs)

    def lazy(self) -> Any:
        """A :class:`~almasix.support.lazy.LazyCollection` over these items."""
        from almasix.support.lazy import LazyCollection

        return LazyCollection(self._values_list())

    def dump(self) -> Self:
        """Print the collection's contents and keep going (Laravel ``dump``)."""
        from almasix.debug import dump

        # Report the caller's frame, not this method's.
        dump(self.all(), _depth=2)
        return self

    def dd(self) -> None:
        """Print the collection's contents and halt (Laravel ``dd``)."""
        from almasix.debug import dd

        dd(self.all())

    def to_pretty_json(self, **kwargs: Any) -> str:
        kwargs.setdefault("indent", 4)
        return self.to_json(**kwargs)

    @classmethod
    def from_json(cls, payload: str, **kwargs: Any) -> Self:
        return cls(json.loads(payload, **kwargs))

    def get(self, key: Any, default: Any = None) -> Any:
        return self._items.get(key, default)

    def has(self, *keys: Any) -> bool:
        return all(key in self._items for key in keys)

    def has_any(self, *keys: Any) -> bool:
        flat = keys[0] if len(keys) == 1 and isinstance(keys[0], (list, tuple)) else keys
        return any(key in self._items for key in flat)

    def keys(self) -> Self:
        return self._new(list(self._items.keys()))

    def values(self) -> Self:
        return self._new(self._values_list())

    def first(self, callback: Callable[[Any], bool] | Any = None, default: Any = None) -> Any:
        # Eloquent-compat: first(default) when the sole arg is not callable.
        if callback is not None and not callable(callback):
            default = callback
            callback = None
        if callback is None:
            return next(iter(self._items.values()), default)
        for item in self._items.values():
            if callback(item):
                return item
        return default

    def last(self, callback: Callable[[Any], bool] | Any = None, default: Any = None) -> Any:
        if callback is not None and not callable(callback):
            default = callback
            callback = None
        values = self._values_list()
        if callback is None:
            return values[-1] if values else default
        for item in reversed(values):
            if callback(item):
                return item
        return default

    def value(self, key: str, default: Any = None) -> Any:
        first = self.first()
        return data_get(first, key, default) if first is not None else default

    def is_empty(self) -> bool:
        return not self._items

    def is_not_empty(self) -> bool:
        return bool(self._items)

    def count(self) -> int:
        return len(self._items)

    def contains(self, key: Any, operator: Any = None, value: Any = None) -> bool:
        if callable(key) and operator is None:
            return any(key(item) for item in self._items.values())
        if operator is None and value is None:
            return key in self._items.values() or key in self._items
        if value is None:
            return any(data_get(item, str(key)) == operator for item in self._items.values())
        return any(
            _compare(data_get(item, str(key)), str(operator), value)
            for item in self._items.values()
        )

    def contains_strict(self, value: Any) -> bool:
        return any(item is value for item in self._items.values())

    def contains_one_item(self) -> bool:
        return len(self._items) == 1

    def doesnt_contain(self, *args: Any, **kwargs: Any) -> bool:
        return not self.contains(*args, **kwargs)

    def doesnt_contain_strict(self, value: Any) -> bool:
        return not self.contains_strict(value)

    def some(self, *args: Any, **kwargs: Any) -> bool:
        return self.contains(*args, **kwargs)

    # --- transform ----------------------------------------------------------

    def map(self, callback: Callable[..., Any]) -> Self:
        result: OrderedDict[Any, Any] = OrderedDict()
        for key, item in self._items.items():
            try:
                result[key] = callback(item, key)
            except TypeError:
                result[key] = callback(item)
        return self._new(result)

    def map_with_keys(self, callback: Callable[..., Any]) -> Self:
        result: OrderedDict[Any, Any] = OrderedDict()
        for key, item in self._items.items():
            try:
                pair = callback(item, key)
            except TypeError:
                pair = callback(item)
            if isinstance(pair, Mapping):
                result.update(pair)
            else:
                new_key, new_value = pair
                result[new_key] = new_value
        return self._new(result)

    def map_into(self, cls: type) -> Self:
        return self.map(lambda item: cls(item))

    def map_to_groups(self, callback: Callable[..., Any]) -> Self:
        groups: OrderedDict[Any, list[Any]] = OrderedDict()
        for key, item in self._items.items():
            try:
                pair = callback(item, key)
            except TypeError:
                pair = callback(item)
            if isinstance(pair, Mapping):
                for group_key, group_value in pair.items():
                    groups.setdefault(group_key, []).append(group_value)
            else:
                group_key, group_value = pair
                groups.setdefault(group_key, []).append(group_value)
        return self._new({key: self._new(values) for key, values in groups.items()})

    def map_spread(self, callback: Callable[..., Any]) -> Self:
        return self.map(
            lambda item: callback(*item) if isinstance(item, (list, tuple)) else callback(item)
        )

    def flat_map(self, callback: Callable[[Any], Any]) -> Self:
        return self.map(callback).collapse()

    def filter(self, callback: Callable[..., bool] | None = None) -> Self:
        if callback is None:
            return self._new({k: v for k, v in self._items.items() if v})
        result: OrderedDict[Any, Any] = OrderedDict()
        for key, item in self._items.items():
            try:
                keep = callback(item, key)
            except TypeError:
                keep = callback(item)
            if keep:
                result[key] = item
        return self._new(result)

    def reject(self, callback: Callable[..., bool] | Any) -> Self:
        if not callable(callback):
            return self.filter(lambda item: item != callback)

        def _keep(item: Any, key: Any = None) -> bool:
            try:
                return not callback(item, key)
            except TypeError:
                return not callback(item)

        return self.filter(_keep)

    def each(self, callback: Callable[..., Any]) -> Self:
        for key, item in self._items.items():
            try:
                result = callback(item, key)
            except TypeError:
                result = callback(item)
            if result is False:
                break
        return self

    def each_spread(self, callback: Callable[..., Any]) -> Self:
        for item in self._items.values():
            if isinstance(item, (list, tuple)):
                if callback(*item) is False:  # pragma: no branch
                    break
            elif callback(item) is False:  # pragma: no cover
                break
        return self

    def transform(self, callback: Callable[..., Any]) -> Self:
        for key in list(self._items.keys()):
            item = self._items[key]
            try:
                self._items[key] = callback(item, key)
            except TypeError:
                self._items[key] = callback(item)
        return self

    def reduce(self, callback: Callable[..., Any], initial: Any = None) -> Any:
        iterator = iter(self._items.values())
        if initial is None:
            try:
                carry = next(iterator)
            except StopIteration:
                return None
        else:
            carry = initial
        for item in iterator:
            carry = callback(carry, item)
        return carry

    def reduce_spread(self, callback: Callable[..., Any], initial: Any = None) -> Any:
        """Reduce where each item is a list/tuple spread into the callback."""

        def _wrapped(carry: Any, item: Any) -> Any:
            if isinstance(item, (list, tuple)):
                return callback(carry, *item)
            return callback(carry, item)

        return self.reduce(_wrapped, initial)

    def multiply(self, times: int) -> Self:
        if times <= 0:
            return self._new([])
        values = self._values_list()
        return self._new(values * times)

    def pipe(self, callback: Callable[[Self], Any]) -> Any:
        return callback(self)

    def pipe_into(self, cls: type) -> Any:
        return cls(self)

    def pipe_through(self, callbacks: Iterable[Callable[[Any], Any]]) -> Any:
        result: Any = self
        for callback in callbacks:
            result = callback(result)
        return result

    def tap(self, callback: Callable[[Self], Any]) -> Self:
        callback(self)
        return self

    def collect(self) -> Self:
        return self._new(self._items)

    # --- where family -------------------------------------------------------

    def where(self, key: str, operator: Any = None, value: Any = None) -> Self:
        if value is None:
            value = operator
            operator = "="
        return self.filter(lambda item: _compare(data_get(item, key), operator, value))

    def where_strict(self, key: str, value: Any) -> Self:
        return self.filter(lambda item: data_get(item, key) is value)

    def where_in(self, key: str, values: Iterable[Any]) -> Self:
        allowed = set(values) if not isinstance(values, set) else values
        return self.filter(lambda item: data_get(item, key) in allowed)

    def where_in_strict(self, key: str, values: Iterable[Any]) -> Self:
        allowed = list(values)
        return self.filter(lambda item: any(data_get(item, key) is v for v in allowed))

    def where_not_in(self, key: str, values: Iterable[Any]) -> Self:
        allowed = set(values) if not isinstance(values, set) else values
        return self.filter(lambda item: data_get(item, key) not in allowed)

    def where_not_in_strict(self, key: str, values: Iterable[Any]) -> Self:
        allowed = list(values)
        return self.filter(lambda item: all(data_get(item, key) is not v for v in allowed))

    def where_between(self, key: str, values: Sequence[Any]) -> Self:
        low, high = values[0], values[1]

        def _between(item: Any) -> bool:
            current = data_get(item, key)
            return current is not None and low <= current <= high

        return self.filter(_between)

    def where_not_between(self, key: str, values: Sequence[Any]) -> Self:
        low, high = values[0], values[1]

        def _not_between(item: Any) -> bool:
            current = data_get(item, key)
            return current is None or not (low <= current <= high)

        return self.filter(_not_between)

    def where_null(self, key: str) -> Self:
        return self.filter(lambda item: data_get(item, key) is None)

    def where_not_null(self, key: str) -> Self:
        return self.filter(lambda item: data_get(item, key) is not None)

    def where_instance_of(self, cls: type) -> Self:
        return self.filter(lambda item: isinstance(item, cls))

    def first_where(self, key: str, operator: Any = None, value: Any = None) -> Any:
        return self.where(key, operator, value).first()

    def first_or_fail(self, callback: Callable[[Any], bool] | None = None) -> Any:
        item = self.first(callback)
        if item is None:
            raise ItemNotFoundError("Item not found.")
        return item

    def sole(self, callback: Callable[[Any], bool] | None = None) -> Any:
        filtered = self.filter(callback) if callback else self
        if filtered.count() == 0:
            raise ItemNotFoundError("Item not found.")
        if filtered.count() > 1:
            raise MultipleItemsFoundError("Multiple items found.")
        return filtered.first()

    # --- aggregation --------------------------------------------------------

    def sum(self, key: str | Callable[[Any], Any] | None = None) -> Any:
        values = [value_get(item, key) for item in self._items.values()]
        return sum(v for v in values if v is not None)

    def avg(self, key: str | Callable[[Any], Any] | None = None) -> Any:
        values = [
            v for v in (value_get(item, key) for item in self._items.values()) if v is not None
        ]
        return (sum(values) / len(values)) if values else None

    average = avg

    def median(self, key: str | Callable[[Any], Any] | None = None) -> Any:
        values = sorted(
            v for v in (value_get(item, key) for item in self._items.values()) if v is not None
        )
        if not values:
            return None
        return statistics.median(values)

    def mode(self, key: str | Callable[[Any], Any] | None = None) -> Any:
        values = [
            v for v in (value_get(item, key) for item in self._items.values()) if v is not None
        ]
        if not values:
            return None
        counts = Counter(values)
        top = max(counts.values())
        return [value for value, count in counts.items() if count == top]

    def min(self, key: str | Callable[[Any], Any] | None = None) -> Any:
        values = [
            v for v in (value_get(item, key) for item in self._items.values()) if v is not None
        ]
        return min(values) if values else None

    def max(self, key: str | Callable[[Any], Any] | None = None) -> Any:
        values = [
            v for v in (value_get(item, key) for item in self._items.values()) if v is not None
        ]
        return max(values) if values else None

    def count_by(self, callback: Callable[[Any], Any] | str | None = None) -> Self:
        counts: OrderedDict[Any, int] = OrderedDict()
        for item in self._items.values():
            marker = value_get(item, callback) if callback is not None else item
            counts[marker] = counts.get(marker, 0) + 1
        return self._new(counts)

    def percentage(self, callback: Callable[[Any], bool], precision: int = 2) -> float:
        if self.is_empty():
            return 0.0
        matched = self.filter(callback).count()
        return round((matched / self.count()) * 100, precision)

    # --- pluck / group / sort -----------------------------------------------

    def pluck(self, value: str, key: str | None = None) -> Any:
        if key is None:
            return self._new(data_get(item, value) for item in self._items.values())
        return {data_get(item, key): data_get(item, value) for item in self._items.values()}

    def group_by(self, key: str | Callable[[Any], Any]) -> Self:
        groups: OrderedDict[Any, list[Any]] = OrderedDict()
        for item in self._items.values():
            groups.setdefault(value_get(item, key), []).append(item)
        return self._new({marker: self._new(items) for marker, items in groups.items()})

    def key_by(self, key: str | Callable[[Any], Any]) -> Self:
        return self._new({value_get(item, key): item for item in self._items.values()})

    def sort(self, callback: Callable[[Any], Any] | None = None) -> Self:
        values = self._values_list()
        if callback is None:
            return self._new(sorted(values))
        return self._new(sorted(values, key=callback))

    def sort_desc(self) -> Self:
        return self._new(sorted(self._values_list(), reverse=True))

    def sort_by(self, key: str | Callable[[Any], Any], descending: bool = False) -> Self:
        return self._new(
            sorted(self._values_list(), key=lambda item: value_get(item, key), reverse=descending)
        )

    def sort_by_desc(self, key: str | Callable[[Any], Any]) -> Self:
        return self.sort_by(key, descending=True)

    def sort_keys(self) -> Self:
        return self._new(OrderedDict(sorted(self._items.items(), key=lambda pair: pair[0])))

    def sort_keys_desc(self) -> Self:
        return self._new(
            OrderedDict(sorted(self._items.items(), key=lambda pair: pair[0], reverse=True))
        )

    def sort_keys_using(self, callback: Callable[[Any], Any]) -> Self:
        return self._new(
            OrderedDict(sorted(self._items.items(), key=lambda pair: callback(pair[0])))
        )

    def reverse(self) -> Self:
        return self._new(OrderedDict(reversed(list(self._items.items()))))

    def shuffle(self) -> Self:
        values = self._values_list()
        random.shuffle(values)
        return self._new(values)

    # --- slice / chunk / take -----------------------------------------------

    def slice(self, start: int, length: int | None = None) -> Self:
        values = self._values_list()
        if length is None:
            return self._new(values[start:])
        end = start + length if length >= 0 else None
        return self._new(values[start:end])

    def splice(self, offset: int, length: int | None = None, replacement: Any = None) -> Self:
        """Remove a portion and optionally replace; returns the removed chunk."""
        values = self._values_list()
        if length is None:
            length = len(values)
        removed = values[offset : offset + length]
        insert = list(Collection(replacement)._values_list()) if replacement is not None else []
        new_values = values[:offset] + insert + values[offset + length :]
        self._items = OrderedDict(enumerate(new_values))
        return self._new(removed)

    def take(self, limit: int) -> Self:
        values = self._values_list()
        return self._new(values[:limit] if limit >= 0 else values[limit:])

    def take_until(self, callback: Callable[[Any], bool] | Any) -> Self:
        result = []
        for item in self._items.values():
            if callable(callback):
                if callback(item):
                    break
            elif item == callback:
                break
            result.append(item)
        return self._new(result)

    def take_while(self, callback: Callable[[Any], bool]) -> Self:
        result = []
        for item in self._items.values():
            if not callback(item):
                break
            result.append(item)
        return self._new(result)

    def skip(self, count: int) -> Self:
        return self._new(self._values_list()[count:])

    def skip_until(self, callback: Callable[[Any], bool] | Any) -> Self:
        values = self._values_list()
        for index, item in enumerate(values):
            matched = callback(item) if callable(callback) else item == callback
            if matched:
                return self._new(values[index:])
        return self._new([])

    def skip_while(self, callback: Callable[[Any], bool]) -> Self:
        values = self._values_list()
        for index, item in enumerate(values):
            if not callback(item):
                return self._new(values[index:])
        return self._new([])

    def chunk(self, size: int) -> Self:
        if size <= 0:
            raise ValueError("Chunk size must be positive")
        values = self._values_list()
        return self._new(
            self._new(values[index : index + size]) for index in range(0, len(values), size)
        )

    def chunk_while(self, callback: Callable[[Any, Any, list[Any]], bool]) -> Self:
        values = self._values_list()
        if not values:
            return self._new([])
        chunks: list[list[Any]] = [[values[0]]]
        for item in values[1:]:
            if callback(item, chunks[-1][-1], chunks[-1]):
                chunks[-1].append(item)
            else:
                chunks.append([item])
        return self._new(self._new(chunk) for chunk in chunks)

    def sliding(self, size: int = 2, step: int = 1) -> Self:
        values = self._values_list()
        return self._new(
            self._new(values[index : index + size])
            for index in range(0, max(0, len(values) - size + 1), step)
        )

    def split(self, number_of_groups: int) -> Self:
        values = self._values_list()
        if number_of_groups <= 0:
            return self._new([])
        size = len(values) // number_of_groups
        remainder = len(values) % number_of_groups
        groups = []
        index = 0
        for i in range(number_of_groups):
            length = size + (1 if i < remainder else 0)
            groups.append(self._new(values[index : index + length]))
            index += length
        return self._new(groups)

    def split_in(self, number_of_groups: int) -> Self:
        return self.chunk(max(1, -(-len(self._items) // number_of_groups)))

    def for_page(self, page: int, per_page: int) -> Self:
        return self.slice(max(page - 1, 0) * per_page, per_page)

    def nth(self, step: int, offset: int = 0) -> Self:
        return self._new(self._values_list()[offset::step])

    # --- mutate / stack -----------------------------------------------------

    def push(self, *values: Any) -> Self:
        for value in values:
            ints = [key for key in self._items if isinstance(key, int)]
            next_key = (max(ints) + 1) if ints else len(self._items)
            self._items[next_key] = value
        return self

    def put(self, key: Any, value: Any) -> Self:
        self._items[key] = value
        return self

    def prepend(self, value: Any, key: Any = None) -> Self:
        if key is None:
            values = [value, *self._values_list()]
            self._items = OrderedDict(enumerate(values))
        else:
            self._items = OrderedDict([(key, value), *self._items.items()])
        return self

    def pop(self, count: int = 1) -> Any:
        if count == 1:
            if not self._items:
                return None
            key = next(reversed(self._items))
            value = self._items.pop(key)
            self._reindex_list_keys()
            return value
        result = []
        for _ in range(count):
            if not self._items:
                break
            key = next(reversed(self._items))
            result.append(self._items.pop(key))
        result.reverse()
        self._reindex_list_keys()
        return self._new(result)

    def shift(self, count: int = 1) -> Any:
        if count == 1:
            if not self._items:
                return None
            key = next(iter(self._items))
            value = self._items.pop(key)
            self._reindex_list_keys()
            return value
        result = []
        for _ in range(count):
            if not self._items:
                break
            key = next(iter(self._items))
            result.append(self._items.pop(key))
        self._reindex_list_keys()
        return self._new(result)

    def pull(self, key: Any, default: Any = None) -> Any:
        return self._items.pop(key, default)

    def forget(self, *keys: Any) -> Self:
        for key in keys:
            self._items.pop(key, None)
        return self

    # --- set ops ------------------------------------------------------------

    def merge(self, items: Any) -> Self:
        other = _as_items(items)
        merged = OrderedDict(self._items)
        if self._list_like() and Collection(items)._list_like():
            start = len(merged)
            for value in other.values():
                merged[start] = value
                start += 1
        else:
            merged.update(other)
        return self._new(merged)

    def merge_recursive(self, items: Any) -> Self:
        def _merge(left: Any, right: Any) -> Any:
            if isinstance(left, Mapping) and isinstance(right, Mapping):
                result = OrderedDict(left)
                for key, value in right.items():
                    result[key] = _merge(result[key], value) if key in result else value
                return result
            return right

        return self._new(_merge(dict(self._items), dict(_as_items(items))))

    def union(self, items: Any) -> Self:
        # Prefer original collection values when keys collide (Laravel union).
        merged = OrderedDict(self._items)
        for key, value in _as_items(items).items():
            merged.setdefault(key, value)
        return self._new(merged)

    def concat(self, items: Any) -> Self:
        return self.merge(items)

    def combine(self, values: Iterable[Any]) -> Self:
        return self._new(OrderedDict(zip(self._values_list(), list(values), strict=False)))

    def collapse(self) -> Self:
        result: list[Any] = []
        for item in self._items.values():
            if isinstance(item, Collection):
                result.extend(item._values_list())
            elif isinstance(item, Mapping):
                result.extend(item.values())
            elif isinstance(item, Iterable) and not isinstance(item, (str, bytes)):
                result.extend(item)
            else:
                result.append(item)
        return self._new(result)

    def collapse_with_keys(self) -> Self:
        result: OrderedDict[Any, Any] = OrderedDict()
        for item in self._items.values():
            if isinstance(item, Collection):
                result.update(item._items)
            elif isinstance(item, Mapping):
                result.update(item)
        return self._new(result)

    def flatten(self, depth: int | float = float("inf")) -> Self:
        def _flatten(values: Iterable[Any], current: int) -> list[Any]:
            out: list[Any] = []
            for item in values:
                if isinstance(item, Collection):
                    item = item._values_list()
                if isinstance(item, Mapping):
                    item = list(item.values())
                if (
                    isinstance(item, Iterable)
                    and not isinstance(item, (str, bytes))
                    and current < depth
                ):
                    out.extend(_flatten(item, current + 1))
                else:
                    out.append(item)
            return out

        return self._new(_flatten(self._values_list(), 0))

    def flip(self) -> Self:
        return self._new(OrderedDict((value, key) for key, value in self._items.items()))

    def pad(self, size: int, value: Any) -> Self:
        values = self._values_list()
        if size > 0:
            return self._new(values + [value] * max(0, size - len(values)))
        return self._new([value] * max(0, abs(size) - len(values)) + values)

    def zip(self, *items: Any) -> Self:
        arrays = [self._values_list(), *[Collection(item)._values_list() for item in items]]
        return self._new([list(row) for row in zip(*arrays, strict=False)])

    def cross_join(self, *lists: Any) -> Self:
        arrays = [self._values_list(), *[Collection(item)._values_list() for item in lists]]
        return self._new([list(row) for row in product(*arrays)])

    def diff(self, items: Any) -> Self:
        other = set(Collection(items)._values_list())
        return self._new(item for item in self._items.values() if item not in other)

    def diff_assoc(self, items: Any) -> Self:
        other = dict(_as_items(items))
        return self._new({k: v for k, v in self._items.items() if k not in other or other[k] != v})

    def diff_assoc_using(self, items: Any, callback: Callable[[Any, Any], bool]) -> Self:
        other = dict(_as_items(items))
        result: OrderedDict[Any, Any] = OrderedDict()
        for key, value in self._items.items():
            if key not in other or not callback(value, other[key]):
                result[key] = value
        return self._new(result)

    def diff_keys(self, items: Any) -> Self:
        other_keys = set(_as_items(items))
        return self._new({k: v for k, v in self._items.items() if k not in other_keys})

    def intersect(self, items: Any) -> Self:
        other = set(Collection(items)._values_list())
        return self._new(item for item in self._items.values() if item in other)

    def intersect_using(self, items: Any, callback: Callable[[Any, Any], bool]) -> Self:
        other = Collection(items)._values_list()
        return self._new(
            item
            for item in self._items.values()
            if any(callback(item, candidate) for candidate in other)
        )

    def intersect_assoc(self, items: Any) -> Self:
        other = dict(_as_items(items))
        return self._new({k: v for k, v in self._items.items() if k in other and other[k] == v})

    def intersect_assoc_using(self, items: Any, callback: Callable[[Any, Any], bool]) -> Self:
        other = dict(_as_items(items))
        return self._new(
            {k: v for k, v in self._items.items() if k in other and callback(v, other[k])}
        )

    def intersect_by_keys(self, items: Any) -> Self:
        other_keys = set(_as_items(items))
        return self._new({k: v for k, v in self._items.items() if k in other_keys})

    def unique(self, key: str | Callable[[Any], Any] | None = None, strict: bool = False) -> Self:
        seen: list[Any] = []
        result: OrderedDict[Any, Any] = OrderedDict()
        for map_key, item in self._items.items():
            marker = value_get(item, key) if key is not None else item
            exists = any(marker is s for s in seen) if strict else marker in seen
            if not exists:
                seen.append(marker)
                result[map_key] = item
        return self._new(result)

    def unique_strict(self, key: str | Callable[[Any], Any] | None = None) -> Self:
        return self.unique(key, strict=True)

    def duplicates(
        self, key: str | Callable[[Any], Any] | None = None, strict: bool = False
    ) -> Self:
        seen: list[Any] = []
        result: OrderedDict[Any, Any] = OrderedDict()
        for map_key, item in self._items.items():
            marker = value_get(item, key) if key is not None else item
            exists = any(marker is s for s in seen) if strict else marker in seen
            if exists:
                result[map_key] = marker if key is not None else item
            else:
                seen.append(marker)
        return self._new(result)

    def duplicates_strict(self, key: str | Callable[[Any], Any] | None = None) -> Self:
        return self.duplicates(key, strict=True)

    def only(self, *keys: Any) -> Self:
        wanted = keys[0] if len(keys) == 1 and isinstance(keys[0], (list, tuple, set)) else keys
        return self._new({k: self._items[k] for k in wanted if k in self._items})

    def except_(self, *keys: Any) -> Self:
        skipped = set(
            keys[0] if len(keys) == 1 and isinstance(keys[0], (list, tuple, set)) else keys
        )
        return self._new({k: v for k, v in self._items.items() if k not in skipped})

    # alias Laravel except
    def except_keys(self, *keys: Any) -> Self:
        return self.except_(*keys)

    def replace(self, items: Any) -> Self:
        merged = OrderedDict(self._items)
        merged.update(_as_items(items))
        return self._new(merged)

    def replace_recursive(self, items: Any) -> Self:
        return self.merge_recursive(items)

    # --- string / search ----------------------------------------------------

    def implode(self, value: str, glue: str | None = None) -> str:
        if glue is None:
            return value.join(str(item) for item in self._items.values())
        return glue.join(str(data_get(item, value)) for item in self._items.values())

    def join(self, glue: str, final_glue: str = "") -> str:
        values = [str(item) for item in self._items.values()]
        if not values:
            return ""
        if len(values) == 1:
            return values[0]
        if not final_glue:
            return glue.join(values)
        return glue.join(values[:-1]) + final_glue + values[-1]

    def search(self, callback: Callable[[Any], bool] | Any, strict: bool = False) -> Any:
        for key, item in self._items.items():
            if callable(callback):
                if callback(item):
                    return key
            elif strict:
                if item is callback:
                    return key
            elif item == callback:
                return key
        return False

    def select(self, *keys: str) -> Self:
        wanted = keys[0] if len(keys) == 1 and isinstance(keys[0], (list, tuple)) else keys
        return self.map(lambda item: {key: data_get(item, key) for key in wanted})

    def random(self, count: int | None = None) -> Any:
        values = self._values_list()
        if not values:
            return self._new([]) if count is not None else None
        if count is None:
            return random.choice(values)
        if count > len(values):
            count = len(values)
        return self._new(random.sample(values, count))

    def every(self, callback: Callable[[Any], bool]) -> bool:
        return all(callback(item) for item in self._items.values())

    def ensure(self, cls: type) -> Self:
        for item in self._items.values():
            if not isinstance(item, cls):
                raise TypeError(f"Collection item is not an instance of {cls!r}")
        return self

    # --- conditionals -------------------------------------------------------

    def when(
        self,
        condition: Any,
        callback: Callable[[Self], Any],
        default: Callable[[Self], Any] | None = None,
    ) -> Any:
        if condition:
            return callback(self)
        if default is not None:
            return default(self)
        return self

    def when_empty(
        self, callback: Callable[[Self], Any], default: Callable[[Self], Any] | None = None
    ) -> Any:
        return self.when(self.is_empty(), callback, default)

    def when_not_empty(
        self, callback: Callable[[Self], Any], default: Callable[[Self], Any] | None = None
    ) -> Any:
        return self.when(self.is_not_empty(), callback, default)

    def unless(
        self,
        condition: Any,
        callback: Callable[[Self], Any],
        default: Callable[[Self], Any] | None = None,
    ) -> Any:
        return self.when(not condition, callback, default)

    def unless_empty(
        self, callback: Callable[[Self], Any], default: Callable[[Self], Any] | None = None
    ) -> Any:
        return self.when_not_empty(callback, default)

    def unless_not_empty(
        self, callback: Callable[[Self], Any], default: Callable[[Self], Any] | None = None
    ) -> Any:
        return self.when_empty(callback, default)

    # --- nesting / dots -----------------------------------------------------

    def dot(self) -> Self:
        def _dot(prefix: str, value: Any, result: OrderedDict[Any, Any]) -> None:
            if isinstance(value, Collection):
                value = value.all()
            if isinstance(value, Mapping):
                if not value:
                    result[prefix] = {}
                    return
                for key, nested in value.items():
                    path = f"{prefix}.{key}" if prefix else str(key)
                    _dot(path, nested, result)
            elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                if not value:
                    result[prefix] = []
                    return
                for index, nested in enumerate(value):
                    path = f"{prefix}.{index}" if prefix else str(index)
                    _dot(path, nested, result)
            else:
                result[prefix] = value

        result: OrderedDict[Any, Any] = OrderedDict()
        for key, value in self._items.items():
            _dot(str(key), value, result)
        return self._new(result)

    def undot(self) -> Self:
        result: dict[Any, Any] = {}
        for key, value in self._items.items():
            parts = str(key).split(".")
            cursor = result
            for part in parts[:-1]:
                cursor = cursor.setdefault(part, {})
            cursor[parts[-1]] = value
        return self._new(result)

    def partition(self, callback: Callable[[Any], bool]) -> Self:
        passed, failed = [], []
        for item in self._items.values():
            (passed if callback(item) else failed).append(item)
        return self._new([self._new(passed), self._new(failed)])

    def before(self, value: Any) -> Any:
        values = self._values_list()
        try:
            index = values.index(value)
        except ValueError:
            return None
        return values[index - 1] if index > 0 else None

    def after(self, value: Any) -> Any:
        values = self._values_list()
        try:
            index = values.index(value)
        except ValueError:
            return None
        return values[index + 1] if index + 1 < len(values) else None


class ItemNotFoundError(LookupError):
    """Raised by ``first_or_fail`` / ``sole`` when no item matches."""


class MultipleItemsFoundError(LookupError):
    """Raised by ``sole`` when more than one item matches."""


_MESSAGE_SENTINEL = object()

#: The collection methods Laravel exposes as higher order messages.
HIGHER_ORDER_MESSAGES = frozenset(
    {
        "average",
        "avg",
        "contains",
        "each",
        "every",
        "filter",
        "first",
        "flat_map",
        "group_by",
        "key_by",
        "map",
        "max",
        "min",
        "partition",
        "reject",
        "skip_until",
        "skip_while",
        "some",
        "sort_by",
        "sort_by_desc",
        "sum",
        "take_until",
        "take_while",
        "unique",
    }
)


class EmptyMessage:
    """What a higher order message returns for an empty collection.

    The operation never runs its callback when there is nothing to iterate, so
    the result is known up front. It is returned through this wrapper because
    the caller may still be writing either form — ``collection.sum.votes``
    reads it as a value, ``collection.each.notify()`` calls it — and an empty
    result set should not decide which of those crashes.
    """

    __slots__ = ("_result",)

    def __init__(self, result: Any) -> None:
        self._result = result

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._result

    def __getattr__(self, name: str) -> Any:
        member = getattr(self._result, name, _MESSAGE_SENTINEL)
        if member is not _MESSAGE_SENTINEL:
            return member
        return EmptyMessage(self._result)

    def __eq__(self, other: object) -> bool:
        return self._result == other

    def __hash__(self) -> int:
        return hash(self._result) if self._result is not None else 0

    def __bool__(self) -> bool:
        return bool(self._result)

    def __int__(self) -> int:
        return int(self._result)

    def __float__(self) -> float:
        return float(self._result)

    def __len__(self) -> int:
        return len(self._result)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._result)

    def __repr__(self) -> str:
        return repr(self._result)


class BoundMessage:
    """A collection method that also answers higher order messages.

    ``collection.map(fn)`` calls the method. ``collection.map.name`` reads that
    key from every item, and ``collection.each.notify()`` calls that method on
    every item — which of the two you get is decided by looking at the items:
    a callable member is invoked, anything else is read.
    """

    __slots__ = ("_collection", "_func")

    def __init__(self, collection: Any, func: Callable[..., Any]) -> None:
        self._collection = collection
        self._func = func

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._func(self._collection, *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        probe = next(iter(self._collection), _MESSAGE_SENTINEL)
        if probe is _MESSAGE_SENTINEL:
            return EmptyMessage(self._func(self._collection, lambda item: None))

        member = getattr(probe, name, _MESSAGE_SENTINEL)
        if callable(member):

            def invoke(*args: Any, **kwargs: Any) -> Any:
                return self._func(
                    self._collection, lambda item: getattr(item, name)(*args, **kwargs)
                )

            return invoke
        return self._func(self._collection, lambda item: value_get(item, name))

    def __repr__(self) -> str:
        return f"<higher order message {self._func.__name__!r}>"


class HigherOrder:
    """Descriptor that hands out :class:`BoundMessage` for a method."""

    __slots__ = ("_doc", "_func")

    def __init__(self, func: Callable[..., Any]) -> None:
        self._func = func
        self._doc = func.__doc__

    @property
    def __doc__(self) -> str | None:  # type: ignore[override]
        return self._doc

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        if obj is None:
            return self._func
        return BoundMessage(obj, self._func)


def install_higher_order(cls: type) -> None:
    """Wrap a class's own higher-order-capable methods in the descriptor.

    Called for every collection class, so a subclass that overrides ``unique``
    or ``contains`` keeps answering higher order messages.
    """
    for name in list(vars(cls)):
        if name in HIGHER_ORDER_MESSAGES and callable(vars(cls)[name]):
            setattr(cls, name, HigherOrder(vars(cls)[name]))


install_higher_order(Collection)


def collect(items: Any = None) -> Collection[Any]:
    """Create a Support collection (Laravel ``collect()``)."""
    return Collection(items)


def _compare(left: Any, operator: str, right: Any) -> bool:
    ops = {
        "=": left == right,
        "==": left == right,
        "!=": left != right,
        "<>": left != right,
        "<": left is not None and right is not None and left < right,
        "<=": left is not None and right is not None and left <= right,
        ">": left is not None and right is not None and left > right,
        ">=": left is not None and right is not None and left >= right,
        "===": left is right,
        "!==": left is not right,
    }
    return bool(ops.get(str(operator), left == right))
