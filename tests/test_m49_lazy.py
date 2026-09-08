"""M49 part 2 — lazy collections, sync and async."""

from __future__ import annotations

import time
from datetime import datetime, timedelta

import pytest

from almasix.support import collect
from almasix.support.lazy import AsyncLazyCollection, LazyCollection, lazy
from almasix.support.collection import Collection
from tests.orm_support import memory_db  # noqa: F401


def counted(limit: int = 100) -> tuple[list[int], object]:
    """A source that records what was pulled out of it."""
    pulled: list[int] = []

    def source():
        for value in range(limit):
            pulled.append(value)
            yield value

    return pulled, source


# --- construction -------------------------------------------------------------


def test_a_lazy_collection_wraps_an_iterable() -> None:
    assert LazyCollection([1, 2, 3]).all() == [1, 2, 3]
    assert LazyCollection.make(range(3)).all() == [0, 1, 2]
    assert LazyCollection().all() == []


def test_a_lazy_collection_wraps_a_generator_function() -> None:
    def rows():
        yield from ("a", "b")

    assert LazyCollection(rows).all() == ["a", "b"]


def test_an_eager_collection_can_go_lazy() -> None:
    assert collect([1, 2, 3]).lazy().map(lambda value: value * 2).all() == [2, 4, 6]


def test_the_lazy_helper_picks_the_flavour() -> None:
    async def rows():
        yield 1

    assert isinstance(lazy([1, 2]), LazyCollection)
    assert isinstance(lazy(rows), AsyncLazyCollection)


def test_a_repr_names_the_pipeline() -> None:
    assert repr(LazyCollection([1])) == "<LazyCollection>"
    assert repr(LazyCollection([1]).map(str).take(1)) == "<LazyCollection: map -> take>"


# --- laziness -----------------------------------------------------------------


def test_nothing_is_pulled_until_iteration() -> None:
    pulled, source = counted()

    pipeline = LazyCollection(source).map(lambda value: value * 2).take(3)
    assert pulled == []

    assert pipeline.all() == [0, 2, 4]
    assert pulled == [0, 1, 2]


def test_first_stops_at_the_first_match() -> None:
    pulled, source = counted()

    assert LazyCollection(source).first(lambda value: value > 3) == 4
    assert pulled == [0, 1, 2, 3, 4]


def test_each_can_stop_early() -> None:
    seen: list[int] = []

    LazyCollection(range(10)).each(lambda value: seen.append(value) or value < 2)

    assert seen == [0, 1, 2]


def test_a_generator_source_is_spent_after_one_pass() -> None:
    _, source = counted(3)
    pipeline = LazyCollection(source())

    assert pipeline.all() == [0, 1, 2]
    assert pipeline.all() == []


def test_remember_replays_without_touching_the_source_again() -> None:
    pulled, source = counted(3)
    pipeline = LazyCollection(source()).remember()

    assert pipeline.all() == [0, 1, 2]
    assert pipeline.all() == [0, 1, 2]
    assert pulled == [0, 1, 2]


def test_remember_keeps_pulling_where_it_left_off() -> None:
    pulled, source = counted(5)
    pipeline = LazyCollection(source()).remember()

    assert pipeline.take(2).all() == [0, 1]
    assert pulled == [0, 1]
    assert pipeline.all() == [0, 1, 2, 3, 4]


# --- operations ---------------------------------------------------------------


def test_mapping_and_filtering() -> None:
    rows = LazyCollection(range(6))

    assert rows.map(lambda v: v * 3).all() == [0, 3, 6, 9, 12, 15]
    assert rows.filter(lambda v: v % 2 == 0).all() == [0, 2, 4]
    assert rows.filter().all() == [1, 2, 3, 4, 5]
    assert rows.reject(lambda v: v % 2 == 0).all() == [1, 3, 5]


def test_where_and_pluck_read_keys() -> None:
    rows = LazyCollection([{"role": "dev", "n": 1}, {"role": "ops", "n": 2}])

    assert rows.where("role", "ops").pluck("n").all() == [2]


def test_taking_and_skipping() -> None:
    rows = LazyCollection(range(6))

    assert rows.take(2).all() == [0, 1]
    assert rows.skip(4).all() == [4, 5]
    assert rows.take_while(lambda v: v < 3).all() == [0, 1, 2]
    assert rows.take_until(lambda v: v == 3).all() == [0, 1, 2]
    assert rows.skip_while(lambda v: v < 3).all() == [3, 4, 5]
    assert rows.skip_until(lambda v: v == 3).all() == [3, 4, 5]


def test_unique_remembers_only_the_keys_it_has_seen() -> None:
    assert LazyCollection([1, 1, 2, 3, 3]).unique().all() == [1, 2, 3]

    rows = [{"g": "a"}, {"g": "a"}, {"g": "b"}]
    assert LazyCollection(rows).unique("g").count() == 2


def test_chunk_emits_batches_and_the_remainder() -> None:
    batches = LazyCollection(range(7)).chunk(3).all()

    assert [batch.all() for batch in batches] == [[0, 1, 2], [3, 4, 5], [6]]
    assert isinstance(batches[0], Collection)


def test_a_chunk_remainder_travels_through_later_operations() -> None:
    sizes = LazyCollection(range(7)).chunk(3).map(lambda batch: batch.count()).all()

    assert sizes == [3, 3, 1]


def test_tap_each_watches_without_changing() -> None:
    seen: list[int] = []

    assert LazyCollection(range(3)).tap_each(seen.append).all() == [0, 1, 2]
    assert seen == [0, 1, 2]


def test_operations_after_an_early_stop_still_run() -> None:
    # `take` ends the pipeline, but the item it let through must still be mapped.
    assert LazyCollection(range(9)).take(2).map(lambda v: v * 10).all() == [0, 10]
    assert LazyCollection(range(9)).take(2).chunk(5).all()[0].all() == [0, 1]


# --- time-shaped operations ---------------------------------------------------


def test_throttle_spaces_items_out() -> None:
    started = time.monotonic()

    assert LazyCollection(range(3)).throttle(0.02).all() == [0, 1, 2]

    assert time.monotonic() - started >= 0.04


def test_a_throttle_pause_passes_through_later_operations() -> None:
    # The pause is an instruction for the driver, so `map` must not see it as
    # an item and `take` must not count it.
    rows = LazyCollection(range(4))

    assert rows.throttle(0.01).map(lambda v: v * 2).all() == [0, 2, 4, 6]
    assert rows.throttle(0.01).take(2).map(str).all() == ["0", "1"]


def test_a_pause_owed_by_the_tail_is_honoured() -> None:
    # The half-full chunk is emitted after the source is spent, and still has a
    # throttle downstream of it.
    started = time.monotonic()

    batches = LazyCollection(range(4)).chunk(3).throttle(0.02).all()

    assert [batch.count() for batch in batches] == [3, 1]
    assert time.monotonic() - started >= 0.02


def test_each_may_run_to_completion() -> None:
    seen: list[int] = []
    pipeline = LazyCollection(range(3))

    assert pipeline.each(seen.append) is pipeline
    assert seen == [0, 1, 2]


def test_take_until_timeout_stops_enumerating() -> None:
    pulled, source = counted(1000)

    assert LazyCollection(source).take_until_timeout(-1).all() == []
    assert len(pulled) == 1

    assert LazyCollection(range(3)).take_until_timeout(30).all() == [0, 1, 2]


def test_take_until_timeout_accepts_a_datetime() -> None:
    past = datetime.now() - timedelta(seconds=1)
    future = datetime.now() + timedelta(seconds=30)

    assert LazyCollection(range(3)).take_until_timeout(past).all() == []
    assert LazyCollection(range(3)).take_until_timeout(future).all() == [0, 1, 2]


def test_with_heartbeat_fires_at_most_once_per_interval() -> None:
    beats: list[int] = []

    LazyCollection(range(3)).with_heartbeat(0.02, lambda: beats.append(1)).throttle(0.03).all()

    assert beats


def test_with_heartbeat_stays_quiet_when_the_interval_has_not_passed() -> None:
    beats: list[int] = []

    LazyCollection(range(5)).with_heartbeat(30, lambda: beats.append(1)).all()

    assert beats == []


# --- terminals ----------------------------------------------------------------


def test_aggregate_terminals() -> None:
    rows = LazyCollection([{"n": 2}, {"n": 4}, {"n": None}])

    assert rows.sum("n") == 6
    assert rows.avg("n") == 3
    assert rows.average("n") == 3
    assert rows.max("n") == 4
    assert rows.min("n") == 2
    assert rows.count() == 3
    assert LazyCollection(range(4)).reduce(lambda carry, v: (carry or 0) + v) == 6


def test_aggregates_of_nothing_are_none() -> None:
    empty = LazyCollection([])

    assert empty.sum() == 0
    assert empty.avg() is None
    assert empty.max() is None
    assert empty.min() is None
    assert empty.is_empty() is True
    assert empty.is_not_empty() is False


def test_contains_takes_a_value_or_a_callback() -> None:
    rows = LazyCollection(range(4))

    assert rows.contains(2) is True
    assert rows.contains(9) is False
    assert rows.contains(lambda v: v > 2) is True
    assert rows.is_not_empty() is True


def test_collect_materialises_for_the_eager_surface() -> None:
    eager = LazyCollection(range(4)).filter(lambda v: v % 2 == 0).collect()

    assert isinstance(eager, Collection)
    # Sorting needs every item, which is why it lives on the eager collection.
    assert eager.sort_desc().all() == [2, 0]


def test_first_of_nothing_is_none() -> None:
    assert LazyCollection([]).first() is None
    assert LazyCollection([1, 2]).first() == 1


# --- async --------------------------------------------------------------------


async def numbers(limit: int = 6):
    for value in range(limit):
        yield {"n": value}


@pytest.mark.asyncio
async def test_an_async_pipeline_reads_the_same() -> None:
    rows = AsyncLazyCollection(numbers)

    assert await rows.map(lambda row: row["n"]).take(3).all() == [0, 1, 2]
    assert await rows.where("n", 2).count() == 1
    assert await rows.sum("n") == 15
    assert await rows.avg("n") == 2.5
    assert await rows.max("n") == 5
    assert await rows.min("n") == 0


@pytest.mark.asyncio
async def test_async_terminals() -> None:
    rows = AsyncLazyCollection(numbers)

    assert await rows.first(lambda row: row["n"] > 3) == {"n": 4}
    assert await rows.first() == {"n": 0}
    assert await rows.contains(lambda row: row["n"] == 5) is True
    assert await rows.contains({"n": 9}) is False
    assert await rows.is_empty() is False
    assert await rows.is_not_empty() is True
    assert await rows.reduce(lambda carry, row: (carry or 0) + row["n"]) == 15
    assert isinstance(await rows.collect(), Collection)
    assert await AsyncLazyCollection.make(numbers).count() == 6


@pytest.mark.asyncio
async def test_an_async_pipeline_stops_pulling_early() -> None:
    pulled: list[int] = []

    async def watched():
        for value in range(100):
            pulled.append(value)
            yield value

    assert await AsyncLazyCollection(watched).take(2).all() == [0, 1]
    assert pulled == [0, 1]


@pytest.mark.asyncio
async def test_async_each_stops_on_false_and_awaits_callbacks() -> None:
    seen: list[int] = []

    async def record(row):
        seen.append(row["n"])
        return row["n"] < 1

    await AsyncLazyCollection(numbers).each(record)

    assert seen == [0, 1]


@pytest.mark.asyncio
async def test_async_each_accepts_a_plain_callback_and_runs_through() -> None:
    seen: list[int] = []
    pipeline = AsyncLazyCollection(numbers)

    assert await pipeline.each(lambda row: seen.append(row["n"])) is pipeline
    assert seen == [0, 1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_async_pauses_pass_through_later_operations() -> None:
    rows = AsyncLazyCollection([1, 2, 3])

    assert await rows.throttle(0.01).map(lambda v: v * 2).all() == [2, 4, 6]
    assert await rows.throttle(0.01).take(2).map(str).all() == ["1", "2"]

    batches = await AsyncLazyCollection(numbers).chunk(4).throttle(0.02).all()
    assert [batch.count() for batch in batches] == [4, 2]


@pytest.mark.asyncio
async def test_an_async_collection_accepts_a_sync_source_too() -> None:
    assert await AsyncLazyCollection([1, 2, 3]).map(lambda v: v * 2).all() == [2, 4, 6]


@pytest.mark.asyncio
async def test_async_chunks_and_empty_aggregates() -> None:
    batches = await AsyncLazyCollection(numbers).chunk(4).all()
    assert [batch.count() for batch in batches] == [4, 2]

    empty = AsyncLazyCollection([])
    assert await empty.avg() is None
    assert await empty.max() is None
    assert await empty.min() is None
    assert await empty.is_empty() is True
    assert await empty.is_not_empty() is False
    assert await empty.first() is None


@pytest.mark.asyncio
async def test_async_throttle_awaits_between_items() -> None:
    started = time.monotonic()

    assert await AsyncLazyCollection([1, 2, 3]).throttle(0.02).all() == [1, 2, 3]

    assert time.monotonic() - started >= 0.04


@pytest.mark.asyncio
async def test_async_take_until_timeout_stops() -> None:
    assert await AsyncLazyCollection(numbers).take_until_timeout(-1).all() == []


# --- streaming database reads -------------------------------------------------


@pytest.mark.asyncio
async def test_streaming_reads_return_chainable_lazy_collections(memory_db) -> None:
    from almasix.orm import Model, Schema

    class Reading(Model):
        table = "readings"
        fillable = ("label", "value")

    await Schema.create(
        "readings",
        lambda t: (t.id(), t.string("label"), t.integer("value"), t.timestamps()),
    )
    for index in range(5):
        await Reading.create(label=f"r{index}", value=index * 10)

    # `async for` still reads one row at a time, as it did before.
    seen = []
    async for reading in Reading.query().cursor():
        seen.append(reading.value)
    assert seen == [0, 10, 20, 30, 40]

    # And the pipeline applies without buffering the result set.
    assert await Reading.query().cursor().map(lambda r: r.label).take(2).all() == ["r0", "r1"]
    assert await Reading.query().lazy(size=2).sum("value") == 100
    assert await Reading.query().lazy_by_id(size=2).pluck("value").first() == 0

    batches = await Reading.query().cursor(size=2).chunk(2).all()
    assert [batch.count() for batch in batches] == [2, 2, 1]
