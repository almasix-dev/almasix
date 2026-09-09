"""M41 part 3 — aggregating related models."""

from __future__ import annotations

import pytest

from almasix.orm import Model, Schema, relation
from tests.orm_support import memory_db  # noqa: F401


class Writer(Model):
    table = "writers"
    fillable = ("name",)

    @relation
    def entries(self):
        return self.has_many(Entry)


class Entry(Model):
    table = "entries"
    fillable = ("writer_id", "title", "votes", "published")

    @relation
    def writer(self):
        return self.belongs_to(Writer)


async def _seed() -> tuple[Writer, Writer, Writer]:
    await Schema.create("writers", lambda t: (t.id(), t.string("name"), t.timestamps()))
    await Schema.create(
        "entries",
        lambda t: (
            t.id(),
            t.foreign_id("writer_id"),
            t.string("title"),
            t.integer("votes").default(0),
            t.integer("published").default(1),
            t.timestamps(),
        ),
    )
    ada = await Writer.create(name="Ada")
    grace = await Writer.create(name="Grace")
    silent = await Writer.create(name="Silent")

    await Entry.create(writer_id=ada.id, title="One", votes=10, published=1)
    await Entry.create(writer_id=ada.id, title="Two", votes=30, published=0)
    await Entry.create(writer_id=grace.id, title="Three", votes=5, published=1)
    return ada, grace, silent


# --- eager aggregates ---------------------------------------------------------


@pytest.mark.asyncio
async def test_with_count_still_counts(memory_db) -> None:
    await _seed()

    writers = await Writer.query().with_count("entries").get()

    assert [writer.entries_count for writer in writers] == [2, 1, 0]


@pytest.mark.asyncio
async def test_with_sum_avg_min_and_max(memory_db) -> None:
    await _seed()

    writers = await (
        Writer.query()
        .with_sum("entries", "votes")
        .with_avg("entries", "votes")
        .with_min("entries", "votes")
        .with_max("entries", "votes")
        .get()
    )

    assert [writer.entries_sum_votes for writer in writers] == [40, 5, None]
    assert [writer.entries_avg_votes for writer in writers] == [20, 5, None]
    assert [writer.entries_min_votes for writer in writers] == [10, 5, None]
    assert [writer.entries_max_votes for writer in writers] == [30, 5, None]


@pytest.mark.asyncio
async def test_with_exists_reports_a_boolean(memory_db) -> None:
    await _seed()

    writers = await Writer.query().with_exists("entries").get()

    assert [writer.entries_exists for writer in writers] == [True, True, False]


@pytest.mark.asyncio
async def test_aggregates_accept_constraining_callbacks(memory_db) -> None:
    await _seed()

    writers = await (
        Writer.query().with_count(entries=lambda query: query.where("published", "=", 1)).get()
    )

    assert [writer.entries_count for writer in writers] == [1, 1, 0]


@pytest.mark.asyncio
async def test_aggregates_accept_mappings_with_aliases(memory_db) -> None:
    await _seed()

    writers = await (
        Writer.query()
        .with_count({"entries as published_count": lambda query: query.where("published", "=", 1)})
        .with_count("entries")
        .get()
    )

    assert [writer.published_count for writer in writers] == [1, 1, 0]
    assert [writer.entries_count for writer in writers] == [2, 1, 0]


@pytest.mark.asyncio
async def test_with_aggregate_takes_an_explicit_alias_and_function(memory_db) -> None:
    await _seed()

    writers = await Writer.query().with_aggregate("entries", "sum", "votes", "score").get()

    assert [writer.score for writer in writers] == [40, 5, None]


@pytest.mark.asyncio
async def test_aggregates_survive_a_custom_select(memory_db) -> None:
    await _seed()

    writers = await Writer.query().select("id", "name").with_count("entries").get()

    assert [writer.entries_count for writer in writers] == [2, 1, 0]


@pytest.mark.asyncio
async def test_several_aggregates_coexist_on_one_query(memory_db) -> None:
    await _seed()

    writer = await Writer.query().with_count("entries").with_sum("entries", "votes").first()

    assert writer.entries_count == 2
    assert writer.entries_sum_votes == 40


# --- deferred aggregates ------------------------------------------------------


@pytest.mark.asyncio
async def test_load_count_on_a_model(memory_db) -> None:
    ada, _, silent = await _seed()

    await ada.load_count("entries")
    await silent.load_count("entries")

    assert ada.entries_count == 2
    assert silent.entries_count == 0


@pytest.mark.asyncio
async def test_load_sum_avg_min_max_and_exists_on_a_model(memory_db) -> None:
    ada, _, silent = await _seed()

    await ada.load_sum("entries", "votes")
    await ada.load_avg("entries", "votes")
    await ada.load_min("entries", "votes")
    await ada.load_max("entries", "votes")
    await ada.load_exists("entries")
    await silent.load_exists("entries")

    assert ada.entries_sum_votes == 40
    assert ada.entries_avg_votes == 20
    assert ada.entries_min_votes == 10
    assert ada.entries_max_votes == 30
    assert ada.entries_exists is True
    assert silent.entries_exists is False


@pytest.mark.asyncio
async def test_load_aggregate_takes_the_function_by_name(memory_db) -> None:
    ada, _, _ = await _seed()

    await ada.load_aggregate("entries", "votes", "max")

    assert ada.entries_max_votes == 30


@pytest.mark.asyncio
async def test_deferred_aggregates_accept_constraints_and_aliases(memory_db) -> None:
    ada, _, _ = await _seed()

    await ada.load_count(entries=lambda query: query.where("published", "=", 1))
    await ada.load_aggregate(["entries as top_score"], "votes", "max", entries=lambda query: query)

    assert ada.entries_count == 1
    assert ada.top_score == 30


@pytest.mark.asyncio
async def test_deferred_aggregates_accept_mappings(memory_db) -> None:
    ada, _, _ = await _seed()

    await ada.load_count({"entries as live_count": lambda query: query.where("published", "=", 1)})

    assert ada.live_count == 1


@pytest.mark.asyncio
async def test_load_count_on_a_collection(memory_db) -> None:
    await _seed()

    writers = await Writer.query().get()
    await writers.load_count("entries")

    assert [writer.entries_count for writer in writers] == [2, 1, 0]


@pytest.mark.asyncio
async def test_collection_supports_the_whole_deferred_family(memory_db) -> None:
    await _seed()

    writers = await Writer.query().get()
    await writers.load_sum("entries", "votes")
    await writers.load_avg("entries", "votes")
    await writers.load_min("entries", "votes")
    await writers.load_max("entries", "votes")
    await writers.load_exists("entries")

    assert [writer.entries_sum_votes for writer in writers] == [40, 5, None]
    assert [writer.entries_avg_votes for writer in writers] == [20, 5, None]
    assert [writer.entries_min_votes for writer in writers] == [10, 5, None]
    assert [writer.entries_max_votes for writer in writers] == [30, 5, None]
    assert [writer.entries_exists for writer in writers] == [True, True, False]


@pytest.mark.asyncio
async def test_deferred_aggregates_on_an_empty_collection_do_nothing(memory_db) -> None:
    await _seed()

    empty = await Writer.query().where("name", "=", "Nobody").get()

    assert await empty.load_count("entries") is empty


@pytest.mark.asyncio
async def test_aggregate_loading_ignores_an_empty_model_list(memory_db) -> None:
    from almasix.orm.eager import eager_load_aggregate

    assert await eager_load_aggregate([], "entries", "entries_count", "count") is None


# --- errors -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_aggregate_functions_are_rejected(memory_db) -> None:
    ada, _, _ = await _seed()

    with pytest.raises(ValueError, match="Unsupported aggregate"):
        await ada.load_aggregate("entries", "votes", "median")


@pytest.mark.asyncio
async def test_column_aggregates_require_a_column(memory_db) -> None:
    ada, _, _ = await _seed()

    with pytest.raises(ValueError, match="needs a column"):
        await ada.load_aggregate("entries", None, "sum")
