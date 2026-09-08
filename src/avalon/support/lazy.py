"""Lazy collections — Laravel's ``LazyCollection`` over sync and async sources.

A lazy collection keeps a source and a list of operations, and applies them one
item at a time while iterating. Nothing runs until you iterate, and only one
item is in memory at a time, which is what makes it usable over a database
cursor or a large file.

Avalon has two of them because reading a row is awaited. :class:`LazyCollection`
wraps an ordinary iterable and behaves exactly like Laravel's. Its async twin,
:class:`AsyncLazyCollection`, wraps an async iterable — ``Model.cursor()`` and
``Model.lazy()`` return one — and its terminal methods are awaited. The
operations in between are identical, and shared, so a pipeline reads the same
either way.

Operations that need every item at once (sorting, grouping) are not lazy by
nature. Rather than pretending, they are absent here: call ``collect()`` to
materialise an eager :class:`~avalon.support.collection.Collection` and use its
full surface.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Self

from avalon.support.collection import Collection, value_get

_STOP = object()
_SKIP = object()


class _Wait(float):
    """A pause the driver performs, so ops stay free of sleeping."""


@dataclass(slots=True)
class _Op:
    """One step in a lazy pipeline."""

    kind: str
    arg: Any = None
    extra: Any = None


def _new_state(op: _Op) -> Any:
    """Per-iteration state for the ops that need to remember something."""
    if op.kind in {"take", "skip"}:
        return 0
    if op.kind == "unique":
        return set()
    if op.kind in {"skip_while", "skip_until"}:
        return False
    if op.kind == "chunk":
        return []
    if op.kind in {"throttle", "with_heartbeat"}:
        return None
    return None


def _step(op: _Op, state: Any, item: Any) -> tuple[Any, list[Any], bool]:
    """Push one item through one operation.

    Returns the new state, the items to pass on, and whether to keep going.
    Emitting a :class:`_Wait` asks the driver to pause; the driver puts the item
    back through the rest of the pipeline afterwards.
    """
    kind = op.kind

    if kind == "map":
        return state, [op.arg(item)], True
    if kind == "filter":
        keep = bool(op.arg(item)) if op.arg is not None else bool(item)
        return state, [item] if keep else [], True
    if kind == "reject":
        return state, [] if bool(op.arg(item)) else [item], True
    if kind == "where":
        return state, [item] if value_get(item, op.arg) == op.extra else [], True
    if kind == "pluck":
        return state, [value_get(item, op.arg)], True
    if kind == "tap_each":
        op.arg(item)
        return state, [item], True

    if kind == "take":
        taken = state + 1
        return taken, [item], taken < op.arg
    if kind == "skip":
        seen = state + 1
        return seen, [] if seen <= op.arg else [item], True
    if kind == "take_while":
        return (state, [item], True) if op.arg(item) else (state, [], False)
    if kind == "take_until":
        return (state, [], False) if op.arg(item) else (state, [item], True)
    if kind == "skip_while":
        if state or not op.arg(item):
            return True, [item], True
        return False, [], True
    if kind == "skip_until":
        if state or op.arg(item):
            return True, [item], True
        return False, [], True

    if kind == "unique":
        key = value_get(item, op.arg) if op.arg is not None else item
        if key in state:
            return state, [], True
        state.add(key)
        return state, [item], True

    if kind == "chunk":
        batch = [*state, item]
        if len(batch) < op.arg:
            return batch, [], True
        return [], [Collection(batch)], True

    if kind == "take_until_timeout":
        alive = time.monotonic() < op.arg
        return state, [item] if alive else [], alive

    if kind == "throttle":
        if state is None:
            return time.monotonic(), [item], True
        due = state + op.arg - time.monotonic()
        return time.monotonic() + max(due, 0.0), [_Wait(max(due, 0.0)), item], True

    if kind == "with_heartbeat":
        now = time.monotonic()
        if state is not None and now - state >= op.arg:
            op.extra()
            return now, [item], True
        return (state if state is not None else now), [item], True

    raise ValueError(f"Unknown lazy operation: {kind!r}")  # pragma: no cover - guard


def _finish(op: _Op, state: Any) -> list[Any]:
    """Whatever an operation still owes when the source runs out."""
    if op.kind == "chunk" and state:
        return [Collection(state)]
    return []


def _deadline(seconds_or_when: Any) -> float:
    """A monotonic deadline from seconds, a datetime, or a timestamp."""
    if isinstance(seconds_or_when, datetime):
        return time.monotonic() + (seconds_or_when - datetime.now(seconds_or_when.tzinfo)).total_seconds()
    return time.monotonic() + float(seconds_or_when)


def _push_item(item: Any, ops: tuple[_Op, ...], states: list[Any]) -> tuple[list[Any], bool]:
    """Push one source item through every operation.

    Returns what came out the far end and whether the source is still worth
    pulling from. A :class:`_Wait` rides along untouched — it is an instruction
    for the driver, not an item for the pipeline.
    """
    pending: list[Any] = [item]
    for index, op in enumerate(ops):
        carried: list[Any] = []
        alive = True
        for value in pending:
            if isinstance(value, _Wait):
                carried.append(value)
                continue
            states[index], emitted, keep_going = _step(op, states[index], value)
            carried.extend(emitted)
            alive = alive and keep_going
        pending = carried
        if not alive:
            return _flush(pending, ops, states, index + 1), False
    return pending, True


def _flush(pending: list[Any], ops: tuple[_Op, ...], states: list[Any], start: int) -> list[Any]:
    """Push the final items through the remaining operations."""
    for index in range(start, len(ops)):
        carried: list[Any] = []
        for value in pending:
            if isinstance(value, _Wait):
                carried.append(value)
                continue
            states[index], emitted, _ = _step(ops[index], states[index], value)
            carried.extend(emitted)
        pending = carried
    return [*pending, *_tail(ops, states, start)]


def _tail(ops: tuple[_Op, ...], states: list[Any], start: int = 0) -> list[Any]:
    """What the pipeline still owes once the source is exhausted.

    A half-filled `chunk` is the case that matters: it is owed by its own
    operation, and then has to travel through everything downstream of it.
    """
    owed: list[Any] = []
    for index in range(start, len(ops)):
        carried: list[Any] = []
        for value in owed:
            states[index], emitted, _ = _step(ops[index], states[index], value)
            carried.extend(emitted)
        owed = [*carried, *_finish(ops[index], states[index])]
    return owed


class LazyOperations:
    """The chainable half of a lazy collection, shared by both flavours."""

    __slots__ = ("_ops", "_source")

    def __init__(self, source: Any = (), ops: tuple[_Op, ...] = ()) -> None:
        self._source = source
        self._ops = ops

    def _push(self, kind: str, arg: Any = None, extra: Any = None) -> Self:
        return type(self)(self._source, (*self._ops, _Op(kind, arg, extra)))

    def _resolved_source(self) -> Any:
        source = self._source
        return source() if callable(source) else source

    def map(self, callback: Callable[[Any], Any]) -> Self:
        """Transform every item as it passes."""
        return self._push("map", callback)

    def filter(self, callback: Callable[[Any], Any] | None = None) -> Self:
        """Keep the items the callback accepts, or the truthy ones."""
        return self._push("filter", callback)

    def reject(self, callback: Callable[[Any], Any]) -> Self:
        """Drop the items the callback accepts."""
        return self._push("reject", callback)

    def where(self, key: str, value: Any) -> Self:
        """Keep items whose ``key`` equals ``value``."""
        return self._push("where", key, value)

    def pluck(self, key: str) -> Self:
        """Read one key from every item."""
        return self._push("pluck", key)

    def take(self, count: int) -> Self:
        """Stop after ``count`` items."""
        return self._push("take", count)

    def skip(self, count: int) -> Self:
        """Ignore the first ``count`` items."""
        return self._push("skip", count)

    def take_while(self, callback: Callable[[Any], Any]) -> Self:
        """Take items until the callback fails."""
        return self._push("take_while", callback)

    def take_until(self, callback: Callable[[Any], Any]) -> Self:
        """Take items until the callback passes."""
        return self._push("take_until", callback)

    def skip_while(self, callback: Callable[[Any], Any]) -> Self:
        """Skip items while the callback passes."""
        return self._push("skip_while", callback)

    def skip_until(self, callback: Callable[[Any], Any]) -> Self:
        """Skip items until the callback passes."""
        return self._push("skip_until", callback)

    def unique(self, key: str | None = None) -> Self:
        """Drop repeats as they arrive, remembering only the keys seen."""
        return self._push("unique", key)

    def chunk(self, size: int) -> Self:
        """Group items into collections of ``size`` as they pass."""
        return self._push("chunk", size)

    def tap_each(self, callback: Callable[[Any], Any]) -> Self:
        """Run a callback for each item as it passes, without changing it."""
        return self._push("tap_each", callback)

    def throttle(self, seconds: float) -> Self:
        """Space items out, for a rate-limited consumer downstream."""
        return self._push("throttle", seconds)

    def take_until_timeout(self, when: Any) -> Self:
        """Stop enumerating once ``when`` passes — seconds or a datetime."""
        return self._push("take_until_timeout", _deadline(when))

    def with_heartbeat(self, seconds: float, callback: Callable[[], Any]) -> Self:
        """Call ``callback`` at most every ``seconds`` while enumerating."""
        return self._push("with_heartbeat", seconds, callback)

    def __repr__(self) -> str:
        steps = " -> ".join(op.kind for op in self._ops)
        return f"<{type(self).__name__}{': ' + steps if steps else ''}>"


class LazyCollection(LazyOperations):
    """Laravel's ``LazyCollection`` over an ordinary iterable or generator."""

    __slots__ = ()

    @classmethod
    def make(cls, source: Any = ()) -> LazyCollection:
        return cls(source)

    def __iter__(self) -> Iterator[Any]:
        states = [_new_state(op) for op in self._ops]
        for item in iter(self._resolved_source()):
            emitted, keep_pulling = _push_item(item, self._ops, states)
            for value in emitted:
                if isinstance(value, _Wait):
                    time.sleep(float(value))
                    continue
                yield value
            if not keep_pulling:
                return
        for value in _tail(self._ops, states):
            if isinstance(value, _Wait):
                time.sleep(float(value))
                continue
            yield value

    # --- terminals ----------------------------------------------------------

    def all(self) -> list[Any]:
        """Enumerate everything into a list."""
        return list(self)

    def collect(self) -> Collection[Any]:
        """Materialise into an eager collection, for the methods that need one."""
        return Collection(self.all())

    def each(self, callback: Callable[[Any], Any]) -> LazyCollection:
        """Run a callback for every item; returning ``False`` stops early."""
        for item in self:
            if callback(item) is False:
                break
        return self

    def first(self, callback: Callable[[Any], Any] | None = None) -> Any:
        """The first item, or the first one the callback accepts."""
        for item in self:
            if callback is None or callback(item):
                return item
        return None

    def count(self) -> int:
        return sum(1 for _ in self)

    def sum(self, key: str | Callable[[Any], Any] | None = None) -> Any:
        return sum(v for v in (value_get(i, key) for i in self) if v is not None)

    def avg(self, key: str | Callable[[Any], Any] | None = None) -> Any:
        values = [v for v in (value_get(i, key) for i in self) if v is not None]
        return sum(values) / len(values) if values else None

    average = avg

    def max(self, key: str | Callable[[Any], Any] | None = None) -> Any:
        values = [v for v in (value_get(i, key) for i in self) if v is not None]
        return max(values) if values else None

    def min(self, key: str | Callable[[Any], Any] | None = None) -> Any:
        values = [v for v in (value_get(i, key) for i in self) if v is not None]
        return min(values) if values else None

    def reduce(self, callback: Callable[[Any, Any], Any], initial: Any = None) -> Any:
        carry = initial
        for item in self:
            carry = callback(carry, item)
        return carry

    def contains(self, needle: Any) -> bool:
        check = needle if callable(needle) else lambda item: item == needle
        return any(check(item) for item in self)

    def is_empty(self) -> bool:
        return self.first() is None

    def is_not_empty(self) -> bool:
        return not self.is_empty()

    def remember(self) -> LazyCollection:
        """Cache what has been enumerated, so a second pass costs nothing.

        Without it, iterating twice runs the source twice — and for a generator
        that means the second pass is empty.
        """
        return LazyCollection(_Remembered(self))


class AsyncLazyCollection(LazyOperations):
    """A lazy collection over an async source, with awaited terminals."""

    __slots__ = ()

    @classmethod
    def make(cls, source: Any = ()) -> AsyncLazyCollection:
        return cls(source)

    async def __aiter__(self) -> AsyncIterator[Any]:
        states = [_new_state(op) for op in self._ops]
        source = self._resolved_source()
        if not hasattr(source, "__aiter__"):
            source = _as_async(source)
        async for item in source:
            emitted, keep_pulling = _push_item(item, self._ops, states)
            for value in emitted:
                if isinstance(value, _Wait):
                    await asyncio.sleep(float(value))
                    continue
                yield value
            if not keep_pulling:
                return
        for value in _tail(self._ops, states):
            if isinstance(value, _Wait):
                await asyncio.sleep(float(value))
                continue
            yield value

    # --- terminals ----------------------------------------------------------

    async def all(self) -> list[Any]:
        return [item async for item in self]

    async def collect(self) -> Collection[Any]:
        return Collection(await self.all())

    async def each(self, callback: Callable[[Any], Any]) -> AsyncLazyCollection:
        async for item in self:
            outcome = callback(item)
            if hasattr(outcome, "__await__"):
                outcome = await outcome
            if outcome is False:
                break
        return self

    async def first(self, callback: Callable[[Any], Any] | None = None) -> Any:
        async for item in self:
            if callback is None or callback(item):
                return item
        return None

    async def count(self) -> int:
        total = 0
        async for _ in self:
            total += 1
        return total

    async def _values(self, key: Any) -> list[Any]:
        return [v for v in [value_get(i, key) async for i in self] if v is not None]

    async def sum(self, key: str | Callable[[Any], Any] | None = None) -> Any:
        return sum(await self._values(key))

    async def avg(self, key: str | Callable[[Any], Any] | None = None) -> Any:
        values = await self._values(key)
        return sum(values) / len(values) if values else None

    average = avg

    async def max(self, key: str | Callable[[Any], Any] | None = None) -> Any:
        values = await self._values(key)
        return max(values) if values else None

    async def min(self, key: str | Callable[[Any], Any] | None = None) -> Any:
        values = await self._values(key)
        return min(values) if values else None

    async def reduce(self, callback: Callable[[Any, Any], Any], initial: Any = None) -> Any:
        carry = initial
        async for item in self:
            carry = callback(carry, item)
        return carry

    async def contains(self, needle: Any) -> bool:
        check = needle if callable(needle) else lambda item: item == needle
        async for item in self:
            if check(item):
                return True
        return False

    async def is_empty(self) -> bool:
        return await self.first() is None

    async def is_not_empty(self) -> bool:
        return not await self.is_empty()


async def _as_async(source: Iterable[Any]) -> AsyncIterator[Any]:
    for item in source:
        yield item


class _Remembered:
    """Replays what has been seen, then keeps pulling from the source."""

    __slots__ = ("_cache", "_done", "_iterator", "_source")

    def __init__(self, source: LazyCollection) -> None:
        self._source = source
        self._cache: list[Any] = []
        self._iterator: Iterator[Any] | None = None
        self._done = False

    def __call__(self) -> Iterator[Any]:
        return self._iterate()

    def _iterate(self) -> Iterator[Any]:
        yield from self._cache
        if self._done:
            return
        if self._iterator is None:
            self._iterator = iter(self._source)
        for item in self._iterator:
            self._cache.append(item)
            yield item
        self._done = True


def lazy(source: Any = ()) -> LazyCollection | AsyncLazyCollection:
    """Wrap a source in the lazy collection that fits it."""
    probe = source() if callable(source) and not isinstance(source, type) else source
    if hasattr(probe, "__aiter__"):
        return AsyncLazyCollection(probe)
    return LazyCollection(probe)


__all__ = ["AsyncLazyCollection", "LazyCollection", "lazy"]
