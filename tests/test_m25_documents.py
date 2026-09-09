"""M25 documents — stores, the document builder, `Document`, and embeds."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest

from almasix.orm import (
    DatabaseManager,
    Document,
    EmbeddedDocument,
    Factory,
    HasFactory,
    SoftDeletes,
    set_manager,
)
from almasix.orm.builder import ModelNotFoundError
from almasix.orm.connection import ConnectionError_
from almasix.orm.documents import (
    Condition,
    DocumentBuilder,
    MemoryStore,
    MongoStore,
    Order,
    Query,
    UnsupportedQueryError,
    dotted,
)
from almasix.orm.documents.filters import has_path
from almasix.orm.documents.stores.memory import matches, new_key
from almasix.orm.documents.stores.mongo import (
    MongoNotInstalled,
    build_dsn,
    to_filter,
    to_sort,
)
from almasix.orm.model import relation

pytestmark = pytest.mark.anyio


# --- the documents under test ---------------------------------------------


class Address(EmbeddedDocument):
    fields = ("city", "country")


class Tag(EmbeddedDocument):
    pass


class Author(HasFactory, Document):
    connection = "docs"
    collection = "authors"
    fillable = ("name", "country", "followers")

    @relation
    def articles(self) -> Any:
        return self.has_many(Article, "author_id", "_id")

    @relation
    def address(self) -> Any:
        return self.embeds_one(Address)

    @relation
    def tags(self) -> Any:
        return self.embeds_many(Tag)


class Article(SoftDeletes, Document):
    connection = "docs"
    fillable = ("title", "author_id", "views", "labels", "meta")

    indexes = ({"keys": [("title", 1)], "unique": True, "name": "title_unique"},)

    @relation
    def author(self) -> Any:
        return self.belongs_to(Author, "author_id", "_id")

    @classmethod
    def scope_popular(cls, builder: DocumentBuilder, floor: int = 10) -> DocumentBuilder:
        return builder.where("views", ">=", floor)


class AuthorFactory(Factory):
    model = Author

    def definition(self) -> dict[str, Any]:
        return {"name": self.fake.name(), "country": "KE"}


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
async def documents() -> AsyncIterator[DatabaseManager]:
    manager = DatabaseManager(
        {
            "default": "sqlite",
            "connections": {
                "sqlite": {"driver": "sqlite", "database": ":memory:"},
                "docs": {"driver": "memory"},
                "second": {"driver": "memory"},
                "mongo": {"driver": "mongodb", "database": "almasix_test"},
            },
        }
    )
    set_manager(manager)
    yield manager
    await manager.disconnect()
    set_manager(None)


async def seed_articles() -> Author:
    author = await Author.create(name="Ada", country="GB", followers=900)
    await Article.create(
        title="Notes", author_id=author.get_key(), views=30, labels=["math", "engines"]
    )
    await Article.create(title="Sketches", author_id=author.get_key(), views=5, labels=["math"])
    return author


# --- the query shape --------------------------------------------------------


def test_a_condition_refuses_an_operator_no_store_can_answer() -> None:
    with pytest.raises(UnsupportedQueryError, match="means nothing to a document store"):
        Condition("views", "~=", 3)


def test_dotted_reads_through_maps_and_arrays() -> None:
    document = {"profile": {"city": "Nairobi"}, "labels": ["math", "engines"]}
    assert dotted(document, "profile.city") == "Nairobi"
    assert dotted(document, "labels.1") == "engines"
    assert dotted(document, "labels.9") is None
    assert dotted(document, "labels.x") is None
    assert dotted(document, "profile.zip") is None
    assert dotted(document, "profile.city.first") is None


def test_has_path_separates_missing_from_null() -> None:
    document = {"deleted_at": None}
    assert has_path(document, "deleted_at") is True
    assert has_path(document, "published_at") is False
    assert has_path(document, "deleted_at.deep") is False


def test_a_query_clones_without_sharing_its_lists() -> None:
    query = Query("posts", [Condition("a", "=", 1)], [Order("a", "desc")], limit=2, offset=1)
    clone = query.clone()
    clone.wheres.append(Condition("b", "=", 2))
    clone.orders[0].direction = "asc"
    assert len(query.wheres) == 1
    assert query.orders[0].descending is True
    assert clone.limit == 2 and clone.offset == 1


def test_order_reads_its_direction() -> None:
    assert Order("a").descending is False
    assert Order("a", "DESC").descending is True


# --- the memory store -------------------------------------------------------


def test_a_generated_key_looks_like_an_object_id() -> None:
    key = new_key()
    assert len(key) == 24
    int(key, 16)


def test_matching_walks_every_operator() -> None:
    document = {"views": 10, "title": "Notes", "labels": ["a", "b"], "author": None}

    def m(*conditions: Condition) -> bool:
        return matches(document, list(conditions))

    assert m() is True
    assert m(Condition("views", "=", 10))
    assert m(Condition("views", "!=", 3))
    assert m(Condition("views", "<", 20))
    assert m(Condition("views", "<=", 10))
    assert m(Condition("views", ">", 3))
    assert m(Condition("views", ">=", 10))
    assert m(Condition("views", "in", [10, 20]))
    assert m(Condition("views", "not in", [1]))
    assert m(Condition("author", "null"))
    assert m(Condition("views", "not null"))
    assert m(Condition("views", "between", (1, 20)))
    assert m(Condition("views", "not between", (50, 60)))
    assert m(Condition("title", "like", "not%"))
    assert m(Condition("title", "regex", "^No"))
    assert m(Condition("labels", "exists", True))
    assert m(Condition("missing", "exists", False))
    assert m(Condition("labels", "all", ["a"]))
    assert m(Condition("labels", "size", 2))
    assert m(Condition("", "group", [Condition("views", "=", 10)]))
    assert m(Condition("", "raw", lambda row: row["views"] == 10))
    assert m(Condition("views", "=", 3)) is False
    assert m(Condition("labels", "size", 5)) is False


def test_comparisons_against_missing_values_are_false_not_errors() -> None:
    document = {"views": None, "title": "Notes"}
    assert matches(document, [Condition("views", ">", 3)]) is False
    assert matches(document, [Condition("views", "like", "a%")]) is False
    assert matches(document, [Condition("title", ">", 3)]) is False


def test_or_conditions_widen_the_match() -> None:
    document = {"views": 1, "title": "Notes"}
    conditions = [Condition("views", ">", 100), Condition("title", "=", "Notes", "or")]
    assert matches(document, conditions) is True


async def test_the_memory_store_cannot_evaluate_a_native_filter() -> None:
    store = MemoryStore()
    await store.insert("posts", [{"title": "Notes"}])
    query = Query("posts", [Condition("", "raw", {"title": "Notes"})])
    with pytest.raises(UnsupportedQueryError, match="belongs to a real engine"):
        await store.find(query)


async def test_the_memory_store_enforces_a_unique_index() -> None:
    store = MemoryStore()
    await store.create_index("posts", [("slug", 1)], unique=True)
    await store.insert("posts", [{"slug": "notes"}])
    with pytest.raises(ValueError, match="Duplicate value for unique index"):
        await store.insert("posts", [{"slug": "notes"}])


async def test_a_plain_index_constrains_nothing() -> None:
    store = MemoryStore()
    await store.create_index("posts", [("slug", 1)])
    await store.insert("posts", [{"slug": "notes"}, {"slug": "notes"}])
    assert await store.count(Query("posts")) == 2


async def test_an_index_is_declared_once() -> None:
    store = MemoryStore()
    first = await store.create_index("posts", [("slug", 1)])
    again = await store.create_index("posts", [("slug", 1)])
    assert first == again == "slug_1"
    await store.create_index("posts", [("title", -1)])
    assert [index["name"] for index in await store.indexes("posts")] == ["slug_1", "title_-1"]


async def test_a_unique_index_lets_a_different_value_through() -> None:
    store = MemoryStore()
    await store.create_index("posts", [("slug", 1)], unique=True)
    await store.insert("posts", [{"slug": "notes"}, {"slug": "sketches"}])
    assert await store.count(Query("posts")) == 2


async def test_distinct_keeps_the_first_of_each_value() -> None:
    store = MemoryStore()
    await store.insert("posts", [{"tag": "a", "n": 1}, {"tag": "a", "n": 2}, {"tag": "b"}])
    rows = await store.find(Query("posts", distinct="tag"))
    assert [row["tag"] for row in rows] == ["a", "b"]
    assert rows[0]["n"] == 1


async def test_a_store_drops_and_forgets_collections() -> None:
    store = MemoryStore()
    await store.insert("posts", [{"title": "Notes"}])
    await store.create_index("posts", [("title", 1)])
    assert await store.collections() == ["posts"]
    await store.drop_collection("posts")
    assert await store.collections() == []
    assert await store.indexes("posts") == []

    await store.insert("posts", [{"title": "Notes"}])
    await store.flush()
    assert await store.collections() == []


async def test_aggregates_over_an_empty_match_are_none() -> None:
    store = MemoryStore()
    query = Query("posts")
    assert await store.aggregate(query, "sum", "views") is None
    assert await store.aggregate(query, "count") == 0


async def test_sorting_puts_missing_values_first_and_never_crashes() -> None:
    store = MemoryStore()
    await store.insert("posts", [{"v": 2}, {"v": None}, {"v": 1}])
    rows = await store.find(Query("posts", orders=[Order("v")]))
    assert [row["v"] for row in rows] == [None, 1, 2]
    rows = await store.find(Query("posts", orders=[Order("v", "desc")]))
    assert [row["v"] for row in rows] == [2, 1, None]


async def test_a_store_hands_back_copies_not_its_own_documents() -> None:
    store = MemoryStore()
    await store.insert("posts", [{"title": "Notes"}])
    rows = await store.find(Query("posts"))
    rows[0]["title"] = "Changed"
    assert (await store.find(Query("posts")))[0]["title"] == "Notes"


async def test_counting_respects_the_window() -> None:
    store = MemoryStore()
    await store.insert("posts", [{"n": index} for index in range(5)])
    assert await store.count(Query("posts")) == 5
    assert await store.count(Query("posts", limit=2)) == 2
    assert await store.count(Query("posts", offset=3)) == 2


async def test_a_projection_always_keeps_the_key() -> None:
    store = MemoryStore()
    await store.insert("posts", [{"title": "Notes", "views": 3}])
    row = (await store.find(Query("posts", projection=("title",))))[0]
    assert set(row) == {"title", "_id"}


# --- the document builder ---------------------------------------------------


async def test_a_builder_needs_something_to_query() -> None:
    with pytest.raises(ValueError, match="either a model or a collection name"):
        DocumentBuilder()


async def test_a_collection_can_be_queried_without_a_model(documents: DatabaseManager) -> None:
    builder = DocumentBuilder.for_collection("visits", connection="docs")
    await builder.insert([{"path": "/", "hits": 2}, {"path": "/docs", "hits": 5}])
    rows = await DocumentBuilder.for_collection("visits", connection="docs").order_by("hits").get()
    assert [row["path"] for row in rows] == ["/", "/docs"]
    assert await DocumentBuilder.for_collection("visits", connection="docs").value("path") == "/"


async def test_where_takes_two_or_three_arguments(documents: DatabaseManager) -> None:
    await seed_articles()
    assert await Article.query().where("views", 30).count() == 1
    assert await Article.query().where("views", ">", 10).count() == 1
    assert await Article.query().where({"title": "Notes"}).count() == 1


async def test_where_with_no_value_is_a_mistake_worth_naming(documents: DatabaseManager) -> None:
    with pytest.raises(TypeError, match="where\\(field, value\\)"):
        Article.query().where("views")


async def test_where_none_means_equals_none(documents: DatabaseManager) -> None:
    await seed_articles()
    assert await Article.query().where("meta", None).count() == 2


async def test_a_closure_groups_its_conditions(documents: DatabaseManager) -> None:
    await seed_articles()
    found = await (
        Article.query()
        .where("views", ">", 0)
        .where(lambda query: query.where("title", "Notes").or_where("title", "Sketches"))
        .get()
    )
    assert len(found) == 2

    empty = Article.query().where(lambda query: query)
    assert [where.operator for where in empty.to_query().wheres] == ["null"]  # the scope only


async def test_the_where_family_reaches_the_store(documents: DatabaseManager) -> None:
    await seed_articles()

    async def count(builder: DocumentBuilder) -> int:
        return await builder.count()

    assert await count(Article.query().where_in("views", [5, 30])) == 2
    assert await count(Article.query().where_not_in("views", [5])) == 1
    assert await count(Article.query().where_null("meta")) == 2
    assert await count(Article.query().where_not_null("title")) == 2
    assert await count(Article.query().where_between("views", 1, 10)) == 1
    assert await count(Article.query().where_not_between("views", 1, 10)) == 1
    assert await count(Article.query().where_like("title", "sk%")) == 1
    assert await count(Article.query().where_regex("title", "^No")) == 1
    assert await count(Article.query().where_exists_field("labels")) == 2
    assert await count(Article.query().where_exists_field("subtitle", False)) == 2
    assert await count(Article.query().where_all("labels", ["math", "engines"])) == 1
    assert await count(Article.query().where_size("labels", 1)) == 1
    assert await count(Article.query().where_raw(lambda row: row["views"] > 10)) == 1
    assert await count(Article.query().where("views", 5).or_where("views", 30)) == 2
    assert await count(Article.query().where("views", 5).or_where_in("views", [30])) == 2
    assert await count(Article.query().where("views", 5).or_where_null("meta")) == 2
    assert await count(Article.query().where("views", 5).or_where_not_null("title")) == 2


async def test_a_field_is_named_with_or_without_its_collection(documents: DatabaseManager) -> None:
    await seed_articles()
    assert await Article.query().where("articles.views", 30).count() == 1


async def test_ordering_paging_and_windows(documents: DatabaseManager) -> None:
    await seed_articles()
    assert [a.title for a in await Article.query().order_by("views").get()] == [
        "Sketches",
        "Notes",
    ]
    assert [a.title for a in await Article.query().order_by_desc("views").get()] == [
        "Notes",
        "Sketches",
    ]
    assert (await Article.query().latest("views").first()).title == "Notes"
    assert (await Article.query().oldest("views").first()).title == "Sketches"
    assert Article.query().latest()._orders[0].column == "created_at"
    assert (await Article.query().order_by("views").reorder().first()).title == "Notes"
    assert (await Article.query().order_by("views").reorder("title", "desc").first()).title == (
        "Sketches"
    )
    assert len(await Article.query().limit(1).get()) == 1
    assert len(await Article.query().take(1).get()) == 1
    assert (await Article.query().offset(1).first()).title == "Sketches"
    assert (await Article.query().skip(1).first()).title == "Sketches"
    assert (await Article.query().for_page(2, 1).first()).title == "Sketches"


async def test_select_and_distinct_shape_the_documents(documents: DatabaseManager) -> None:
    await seed_articles()
    row = await Article.query().select("title").first()
    assert row.title == "Notes"
    assert row.get_raw_attribute("views") is None

    rows = await Article.query().select("title").add_select("views").get_raw()
    assert set(rows[0]) == {"title", "views", "_id"}

    countries = await Author.query().distinct("country").get_raw()
    assert [row["country"] for row in countries] == ["GB"]


async def test_conditional_helpers_read_like_the_sql_builder(documents: DatabaseManager) -> None:
    await seed_articles()
    seen: list[str] = []
    query = (
        Article.query()
        .when(True, lambda builder, _: builder.where("views", ">", 10))
        .when(False, lambda builder, _: builder.where("views", 0))
        .when(False, lambda builder, _: builder, lambda builder, _: builder)
        .unless(False, lambda builder, _: builder.where_not_null("title"))
        .tap(lambda builder: seen.append(builder.table))
    )
    assert await query.count() == 1
    assert seen == ["articles"]
    assert Article.query().when(True, lambda builder, _: None) is not None


async def test_a_local_scope_works_on_a_document(documents: DatabaseManager) -> None:
    await seed_articles()
    assert await Article.query().popular().count() == 1
    assert await Article.query().popular(1).count() == 2


async def test_the_builder_says_no_to_sql_only_calls(documents: DatabaseManager) -> None:
    with pytest.raises(UnsupportedQueryError, match="no joins"):
        Article.query().join("authors", "id", "=", "author_id")
    with pytest.raises(UnsupportedQueryError, match="aggregation pipeline"):
        Article.query().group_by("author_id")
    with pytest.raises(UnsupportedQueryError, match="SQL-only"):
        Document.where_column("a", "b")
    with pytest.raises(AttributeError):
        Article.query().not_a_method_at_all
    with pytest.raises(AttributeError):
        Article.query()._nope


async def test_reads_that_return_one_document(documents: DatabaseManager) -> None:
    author = await seed_articles()
    found = await Article.query().where("title", "Notes").first()
    assert found.title == "Notes"
    assert (await Article.query().find(found.get_key())).title == "Notes"
    assert (await Article.query().find_or_fail(found.get_key())).title == "Notes"
    assert (await Article.query().first_or_fail()).title == "Notes"
    assert len(await Article.query().find_many([found.get_key()])) == 1
    assert await Article.query().where("title", "Nothing").first() is None
    assert await Article.query().value("title") == "Notes"
    assert await Article.query().where("title", "Nothing").value("title") is None
    assert await Author.find(author.get_key()) is not None

    with pytest.raises(ModelNotFoundError):
        await Article.query().where("title", "Nothing").first_or_fail()
    with pytest.raises(ModelNotFoundError):
        await Article.query().find_or_fail("missing")
    with pytest.raises(ModelNotFoundError):
        await DocumentBuilder.for_collection("nothing", connection="docs").first_or_fail()


async def test_plucking_counting_and_aggregating(documents: DatabaseManager) -> None:
    await seed_articles()
    assert set((await Article.query().pluck("title")).all()) == {"Notes", "Sketches"}
    keyed = await Article.query().pluck("views", "title")
    assert keyed["Notes"] == 30
    assert await Article.query().count() == 2
    assert await Article.query().count("meta") == 0
    assert await Article.query().sum("views") == 35
    assert await Article.query().avg("views") == 17.5
    assert await Article.query().min("views") == 5
    assert await Article.query().max("views") == 30
    assert await Article.query().exists() is True
    assert await Article.query().where("views", 1).doesnt_exist() is True
    assert len(await Article.query().all()) == 2


async def test_a_pipeline_needs_a_store_that_runs_pipelines(documents: DatabaseManager) -> None:
    await seed_articles()
    with pytest.raises(UnsupportedQueryError, match="no aggregation pipeline"):
        await Article.query().raw_aggregate([{"$match": {}}])

    collection = FakeCollection([{"_id": None, "value": 2}])
    documents.set_store("docs", MongoStore("docs", {}, client=FakeClient(FakeDatabase(collection))))
    assert await Article.query().raw_aggregate([{"$match": {}}]) == [{"_id": None, "value": 3}]
    assert collection.seen["aggregate"] == [{"$match": {}}]


async def test_chunking_and_streaming(documents: DatabaseManager) -> None:
    author = await seed_articles()
    for index in range(3):
        await Article.create(title=f"Extra {index}", author_id=author.get_key(), views=index)

    pages: list[int] = []
    assert await Article.query().chunk(2, lambda rows: pages.append(len(rows))) is True
    assert pages == [2, 2, 1]

    async def count_page(rows: Any) -> None:
        pages.append(len(rows))

    assert await Article.query().chunk(5, count_page) is True
    assert pages[-1] == 5

    async def stop(rows: Any) -> bool:
        return False

    assert await Article.query().chunk(2, stop) is False

    seen: list[str] = []
    assert await Article.query().each(lambda article: seen.append(article.title), 2) is True
    assert len(seen) == 5
    assert await Article.query().each(lambda article: False, 2) is False

    async def note(article: Any) -> None:
        seen.append(article.title)

    assert await Article.query().each(note, 10) is True
    assert len(seen) == 10

    lazily = [article.title async for article in Article.query().lazy(2)]
    assert len(lazily) == 5

    exact = [article.title async for article in Article.query().lazy(5)]
    assert len(exact) == 5


async def test_pagination_over_documents(documents: DatabaseManager) -> None:
    await seed_articles()
    page = await Article.query().order_by("views").paginate(1, 2)
    assert page.total == 2
    assert page.current_page == 2
    assert [article.title for article in page.items] == ["Notes"]

    simple = await Article.query().simple_paginate(1, 1)
    assert simple.has_more_pages() is True
    assert await Author.query().paginate() is not None


async def test_writes_through_the_builder(documents: DatabaseManager) -> None:
    assert await Article.query().insert({"title": "One", "views": 1}) == 1
    assert await Article.query().insert([{"title": "Two", "views": 2}]) == 1
    assert await Article.query().insert([]) == 0
    key = await Article.query().insert_get_id({"title": "Three", "views": 3})
    assert await Article.query().where_key(key).count() == 1

    assert await Article.query().where("title", "One").update({"views": 10}) == 1
    assert await Article.query().where("title", "One").increment("views", 5) == 1
    assert await Article.query().where("title", "One").value("views") == 15
    assert await Article.query().where("title", "One").decrement("views") == 1
    assert await Article.query().where("title", "One").value("views") == 14
    assert await Article.query().where("title", "One").delete() == 1

    await Article.query().truncate()
    assert await Article.query().count() == 0


async def test_upsert_inserts_then_updates(documents: DatabaseManager) -> None:
    assert await Article.query().upsert({"title": "One", "views": 1}, ["title"]) == 1
    assert await Article.query().upsert({"title": "One", "views": 9}, ["title"]) == 1
    assert await Article.query().where("title", "One").value("views") == 9
    assert (
        await Article.query().upsert(
            [{"title": "One", "views": 3, "labels": []}], ["title"], ["views"]
        )
        == 1
    )
    assert await Article.query().where("title", "One").value("labels") is None
    assert await Article.query().count() == 1

    with pytest.raises(ValueError, match="requires unique_by"):
        await Article.query().upsert({"title": "One"}, [])


async def test_a_builder_clone_keeps_everything_it_was_given(documents: DatabaseManager) -> None:
    builder = (
        Article.query()
        .where("views", ">", 1)
        .order_by("views")
        .limit(2)
        .offset(1)
        .select("title")
        .distinct("title")
        .with_("author")
        .with_count("author")
        .with_casts({"views": "int"})
        .without_global_scope("soft_deletes")
    )
    clone = builder.clone()
    assert len(clone._wheres) == 1
    assert clone._limit == 2 and clone._offset == 1
    assert clone._selects == ("title",) and clone._distinct == "title"
    assert "author" in clone._eager and clone._eager_counts
    assert clone._casts == {"views": "int"}
    assert clone._without_scopes == {"soft_deletes"}
    assert "articles" in repr(builder)


# --- the document model -----------------------------------------------------


async def test_a_document_names_its_collection(documents: DatabaseManager) -> None:
    assert Author.get_collection() == "authors"
    assert Article.get_table() == "articles"


async def test_the_life_of_a_document(documents: DatabaseManager) -> None:
    article = await Article.create(title="Notes", views=1)
    assert article.exists is True
    assert len(article.get_key()) == 24
    assert article.get_raw_attribute("created_at") is not None

    article.views = 2
    await article.save()
    assert (await Article.find(article.get_key())).views == 2

    fresh = await article.fresh()
    assert fresh.title == "Notes"

    await article.delete()
    assert await Article.query().count() == 0
    assert await Article.with_trashed().count() == 1
    await article.restore()
    assert await Article.query().count() == 1
    await article.force_delete()
    assert await Article.with_trashed().count() == 0


async def test_a_key_given_by_hand_is_kept(documents: DatabaseManager) -> None:
    article = Article(title="Notes")
    article.set_attribute("_id", "given-key")
    await article.save()
    assert (await Article.find("given-key")).title == "Notes"


async def test_events_and_observers_fire_for_documents(documents: DatabaseManager) -> None:
    seen: list[str] = []
    Article.listen("creating", lambda article: seen.append("creating"))
    Article.listen("created", lambda article: seen.append("created"))
    try:
        await Article.create(title="Watched")
        assert seen == ["creating", "created"]
    finally:
        Article._events = {event: [] for event in Article._events}


async def test_a_refused_creating_event_writes_nothing(documents: DatabaseManager) -> None:
    Article.listen("creating", lambda article: False)
    try:
        article = Article(title="Refused")
        assert await article.save() is False
        assert await Article.query().count() == 0
    finally:
        Article._events = {event: [] for event in Article._events}


async def test_a_document_can_change_its_connection(documents: DatabaseManager) -> None:
    await Author.on("second").insert({"name": "Elsewhere"})
    assert await Author.on("second").count() == 1
    assert await Author.query().count() == 0

    author = Author(name="Moved")
    author.set_connection("second")
    await author.save()
    assert await Author.on("second").count() == 2
    assert Author.new_query()._connection_name == "docs"


async def test_indexes_are_created_from_the_model(documents: DatabaseManager) -> None:
    assert await Article.sync_indexes() == ["title_unique"]
    store = Article.get_store()
    assert (await store.indexes("articles"))[0]["unique"] is True
    await Article.create(title="Notes")
    with pytest.raises(ValueError, match="Duplicate value"):
        await Article.create(title="Notes")


async def test_reference_relations_load_across_documents(documents: DatabaseManager) -> None:
    author = await seed_articles()
    loaded = await Author.query().with_("articles").with_count("articles").first()
    assert [article.title for article in loaded.articles] == ["Notes", "Sketches"]
    assert loaded.articles_count == 2

    article = await Article.query().with_("author").first()
    assert article.author.name == "Ada"

    lazy = await Author.find(author.get_key())
    assert len(await lazy.get_relation("articles").get()) == 2

    counted = await Author.query().with_count("articles as writings").first()
    assert counted.writings == 2

    forgotten = Author.query().with_("articles").without("articles")
    assert forgotten._eager == {}


async def test_relations_can_be_named_in_a_mapping_or_on_the_class(
    documents: DatabaseManager,
) -> None:
    await seed_articles()
    loaded = (
        await Author.query().with_({"articles": lambda query: query.where("views", 30)}).first()
    )
    assert [article.title for article in loaded.articles] == ["Notes"]

    class EagerAuthor(Author):
        collection = "authors"
        with_ = ("articles",)

    always = await EagerAuthor.query().first()
    assert len(always.articles) == 2


def test_a_document_class_says_so(documents: DatabaseManager) -> None:
    from almasix.orm import Model
    from almasix.orm.documents import is_document

    assert is_document(Article) is True
    assert is_document(Model) is False


async def test_serializing_a_document_reads_like_a_model(documents: DatabaseManager) -> None:
    author = await Author.create(name="Ada", country="GB")
    await author.get_relation("address").create(city="London", country="GB")
    payload = (await Author.find(author.get_key())).to_dict()
    assert payload["name"] == "Ada"
    assert payload["address"] == {"city": "London", "country": "GB"}
    assert "_id" in payload


# --- embedded documents -----------------------------------------------------


def test_an_embed_holds_attributes_like_a_small_model() -> None:
    address = Address({"city": "Nairobi"}, country="KE")
    assert address.city == "Nairobi"
    assert address["country"] == "KE"
    address["city"] = "Mombasa"
    address.country = "KE"
    assert address.to_dict() == {"city": "Mombasa", "country": "KE"}
    assert address == Address(city="Mombasa", country="KE")
    assert address != Address(city="Nairobi")
    assert address != "not an embed"
    assert address.fill({"city": "Kisumu"}).city == "Kisumu"
    assert isinstance(hash(address), int)
    assert "Address" in repr(address)


def test_an_embed_refuses_a_field_it_does_not_declare() -> None:
    with pytest.raises(ValueError, match="has no field"):
        Address(city="Nairobi", planet="Earth")
    assert Tag(anything="goes").anything == "goes"


def test_reading_an_attribute_an_embed_has_not_got() -> None:
    address = Address(city="Nairobi")
    with pytest.raises(AttributeError, match="has no attribute 'zip'"):
        address.zip
    with pytest.raises(AttributeError):
        address._secret


def test_hydrating_embeds() -> None:
    assert Address.hydrate(None) is None
    assert Address.hydrate({"city": "Nairobi"}).city == "Nairobi"
    existing = Address(city="Nairobi")
    assert Address.hydrate(existing) is existing
    assert len(Address.hydrate_many([{"city": "A"}, {"city": "B"}])) == 2
    assert Address.hydrate_many(None) == []


def test_a_nested_embed_serializes_all_the_way_down() -> None:
    outer = Tag(name="home", where=Address(city="Nairobi"))
    assert outer.to_dict() == {"name": "home", "where": {"city": "Nairobi"}}


async def test_an_unbound_embed_cannot_save_itself() -> None:
    with pytest.raises(UnsupportedQueryError, match="not embedded in anything"):
        await Address(city="Nairobi").save()


async def test_embeds_one_reads_writes_and_removes(documents: DatabaseManager) -> None:
    author = await Author.create(name="Ada")
    assert author.get_relation("address").get() is None

    await author.get_relation("address").create(city="London", country="GB")
    reloaded = await Author.find(author.get_key())
    address = reloaded.get_relation("address").get()
    assert address.city == "London"

    address.city = "Cambridge"
    await address.save()
    assert (await Author.find(author.get_key())).get_relation("address").get().city == ("Cambridge")

    await reloaded.get_relation("address").delete()
    assert (await Author.find(author.get_key())).get_relation("address").get() is None
    assert "EmbedsOne" in repr(reloaded.get_relation("address"))


async def test_embeds_many_is_a_list_inside_the_document(documents: DatabaseManager) -> None:
    author = await Author.create(name="Ada")
    tags = author.get_relation("tags")
    assert tags.get() == []
    assert tags.first() is None

    await tags.create(name="math")
    await tags.create_many([{"name": "engines"}, {"name": "notes"}])

    reloaded = await Author.find(author.get_key())
    tags = reloaded.get_relation("tags")
    assert [tag.name for tag in tags] == ["math", "engines", "notes"]
    assert len(tags) == 3 and tags.count() == 3
    assert tags.first().name == "math"
    assert [tag.name for tag in tags.where(name="engines")] == ["engines"]

    assert await tags.delete_where(name="engines") == 1
    assert await tags.delete_where(name="nothing") == 0
    assert [tag.name for tag in (await Author.find(author.get_key())).get_relation("tags")] == [
        "math",
        "notes",
    ]

    first = tags.first()
    first.name = "renamed"
    await first.save()
    assert (await Author.find(author.get_key())).get_raw_attribute("tags")[0] == {"name": "renamed"}

    latest = await Author.find(author.get_key())
    tags = latest.get_relation("tags")
    tags.set([{"name": "only"}])
    await latest.save()
    assert (await Author.find(author.get_key())).get_raw_attribute("tags") == [{"name": "only"}]
    assert "EmbedsMany" in repr(tags)


async def test_an_embed_field_can_be_named(documents: DatabaseManager) -> None:
    author = await Author.create(name="Ada")
    home = author.embeds_one(Address, "home")
    home.associate({"city": "Nairobi"})
    await author.save()
    assert (await Author.find(author.get_key())).get_raw_attribute("home")["city"] == "Nairobi"

    places = author.embeds_many(Address, "places")
    places.associate(Address(city="Kisumu"))
    await author.save()
    assert len((await Author.find(author.get_key())).get_raw_attribute("places")) == 1


# --- factories over documents ----------------------------------------------


async def test_a_factory_creates_documents(documents: DatabaseManager) -> None:
    made = await Author.factory().count(2).create()
    assert len(made) == 2
    assert await Author.query().count() == 2
    assert all(author.country == "KE" for author in made)

    unsaved = await Author.factory().make({"name": "Ada"})
    assert unsaved.exists is False


# --- the Mongo translation --------------------------------------------------


def test_a_dsn_is_built_from_the_connection_config() -> None:
    assert build_dsn({"dsn": "mongodb://given/"}) == "mongodb://given/"
    assert build_dsn({"url": "mongodb://url/"}) == "mongodb://url/"
    assert build_dsn({}) == "mongodb://127.0.0.1:27017"
    assert build_dsn({"host": "db", "port": 1}) == "mongodb://db:1"
    assert build_dsn({"username": "a b"}) == "mongodb://a+b@127.0.0.1:27017"
    assert build_dsn({"username": "u", "password": "p@ss"}) == (
        "mongodb://u:p%40ss@127.0.0.1:27017"
    )


def test_every_operator_becomes_a_mongo_filter() -> None:
    assert to_filter([]) == {}
    assert to_filter([Condition("a", "=", 1)]) == {"a": 1}
    assert to_filter([Condition("a", "!=", 1)]) == {"a": {"$ne": 1}}
    assert to_filter([Condition("a", "<", 1)]) == {"a": {"$lt": 1}}
    assert to_filter([Condition("a", "<=", 1)]) == {"a": {"$lte": 1}}
    assert to_filter([Condition("a", ">", 1)]) == {"a": {"$gt": 1}}
    assert to_filter([Condition("a", ">=", 1)]) == {"a": {"$gte": 1}}
    assert to_filter([Condition("a", "in", [1])]) == {"a": {"$in": [1]}}
    assert to_filter([Condition("a", "not in", [1])]) == {"a": {"$nin": [1]}}
    assert to_filter([Condition("a", "null")]) == {"a": None}
    assert to_filter([Condition("a", "not null")]) == {"a": {"$ne": None}}
    assert to_filter([Condition("a", "between", (1, 2))]) == {"a": {"$gte": 1, "$lte": 2}}
    assert to_filter([Condition("a", "not between", (1, 2))]) == {
        "$or": [{"a": {"$lt": 1}}, {"a": {"$gt": 2}}]
    }
    assert to_filter([Condition("a", "like", "no%")]) == {
        "a": {"$regex": "^no.*$", "$options": "i"}
    }
    assert to_filter([Condition("a", "regex", "^n")]) == {"a": {"$regex": "^n"}}
    assert to_filter([Condition("a", "exists", True)]) == {"a": {"$exists": True}}
    assert to_filter([Condition("a", "all", [1])]) == {"a": {"$all": [1]}}
    assert to_filter([Condition("a", "size", 2)]) == {"a": {"$size": 2}}
    assert to_filter([Condition("", "raw", {"$text": {"$search": "x"}})]) == {
        "$text": {"$search": "x"}
    }
    assert to_filter([Condition("", "group", [Condition("a", "=", 1)])]) == {"a": 1}


def test_and_or_and_repeated_fields_survive_translation() -> None:
    assert to_filter([Condition("a", "=", 1), Condition("b", "=", 2)]) == {"a": 1, "b": 2}
    assert to_filter([Condition("a", "=", 1), Condition("b", "=", 2, "or")]) == {
        "$or": [{"a": 1}, {"b": 2}]
    }
    assert to_filter([Condition("a", ">", 1), Condition("a", "<", 5)]) == {
        "$and": [{"a": {"$gt": 1}}, {"a": {"$lt": 5}}]
    }
    assert to_filter([Condition("", "group", []), Condition("a", "=", 1)]) == {"a": 1}
    assert to_filter([Condition("", "group", [])]) == {}


def test_sorting_translates_to_mongo_pairs() -> None:
    query = Query("a", orders=[Order("x"), Order("y", "desc")])
    assert to_sort(query) == [("x", 1), ("y", -1)]


def test_the_mongo_store_says_what_is_missing_when_motor_is_not_installed() -> None:
    assert "almasix[mongodb]" in str(MongoNotInstalled())


class FakeCursor:
    def __init__(self, rows: Sequence[dict[str, Any]]) -> None:
        self.rows = list(rows)
        self.calls: list[tuple[str, Any]] = []

    def sort(self, pairs: Any) -> FakeCursor:
        self.calls.append(("sort", pairs))
        return self

    def skip(self, count: int) -> FakeCursor:
        self.calls.append(("skip", count))
        return self

    def limit(self, count: int) -> FakeCursor:
        self.calls.append(("limit", count))
        return self

    async def __aiter__(self) -> Any:
        for row in self.rows:
            yield row


class FakeResult:
    def __init__(self, **fields: Any) -> None:
        self.__dict__.update(fields)


class FakeCollection:
    def __init__(self, rows: Sequence[dict[str, Any]] | None = None) -> None:
        self.rows = list(rows or [])
        self.seen: dict[str, Any] = {}

    def find(self, filter: Any, projection: Any = None) -> FakeCursor:
        self.seen["find"] = (filter, projection)
        return FakeCursor(self.rows)

    async def distinct(self, field: str, filter: Any) -> list[Any]:
        self.seen["distinct"] = (field, filter)
        return ["a", "b"]

    async def count_documents(self, filter: Any, **options: Any) -> int:
        self.seen["count"] = (filter, options)
        return 7

    def aggregate(self, pipeline: Any) -> FakeCursor:
        self.seen["aggregate"] = pipeline
        return FakeCursor([{"_id": None, "value": 3}])

    async def insert_one(self, row: Any) -> FakeResult:
        self.seen["insert_one"] = row
        return FakeResult(inserted_id="one")

    async def insert_many(self, rows: Any) -> FakeResult:
        self.seen["insert_many"] = rows
        return FakeResult(inserted_ids=["a", "b"])

    async def update_many(self, filter: Any, update: Any) -> FakeResult:
        self.seen["update_many"] = (filter, update)
        return FakeResult(modified_count=2)

    async def delete_many(self, filter: Any) -> FakeResult:
        self.seen["delete_many"] = filter
        return FakeResult(deleted_count=4)

    async def create_index(self, keys: Any, **options: Any) -> str:
        self.seen["create_index"] = (keys, options)
        return "made"

    async def index_information(self) -> dict[str, Any]:
        return {"slug_1": {"key": [("slug", 1)], "unique": True}}


class FakeDatabase:
    def __init__(self, collection: FakeCollection) -> None:
        self.collection = collection
        self.dropped: list[str] = []

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collection

    async def drop_collection(self, name: str) -> None:
        self.dropped.append(name)

    async def list_collection_names(self) -> list[str]:
        return ["b", "a"]


class FakeClient:
    def __init__(self, database: FakeDatabase) -> None:
        self.database = database
        self.closed = False

    def __getitem__(self, name: str) -> FakeDatabase:
        return self.database

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def mongo() -> tuple[MongoStore, FakeCollection, FakeClient]:
    collection = FakeCollection([{"_id": 1, "title": "Notes"}])
    client = FakeClient(FakeDatabase(collection))
    store = MongoStore("mongo", {"database": "almasix_test"}, client=client)
    return store, collection, client


async def test_the_mongo_store_reads(mongo: tuple[MongoStore, FakeCollection, FakeClient]) -> None:
    store, collection, _ = mongo
    query = Query(
        "articles",
        [Condition("title", "=", "Notes")],
        [Order("title", "desc")],
        limit=2,
        offset=1,
        projection=("title",),
    )
    rows = await store.find(query)
    assert rows == [{"_id": 1, "title": "Notes"}]
    assert collection.seen["find"] == ({"title": "Notes"}, {"title": 1})

    assert await store.count(Query("articles", limit=1, offset=2)) == 7
    assert collection.seen["count"][1] == {"skip": 2, "limit": 1}

    assert await store.aggregate(Query("articles"), "sum", "views") == 3
    assert await store.aggregate(Query("articles"), "count") == 7
    assert await store.group_count(Query("articles"), "author_id") == {None: 3}
    assert await store.raw_aggregate("articles", [{"$match": {}}]) == [{"_id": None, "value": 3}]


async def test_a_distinct_query_uses_mongos_own_call(
    mongo: tuple[MongoStore, FakeCollection, FakeClient],
) -> None:
    store, collection, _ = mongo
    rows = await store.find(Query("articles", distinct="country"))
    assert rows == [{"country": "a"}, {"country": "b"}]
    assert collection.seen["distinct"][0] == "country"


async def test_an_empty_aggregate_is_none(
    mongo: tuple[MongoStore, FakeCollection, FakeClient],
) -> None:
    store, collection, _ = mongo
    collection.aggregate = lambda pipeline: FakeCursor([])  # type: ignore[method-assign]
    assert await store.aggregate(Query("articles"), "sum", "views") is None


async def test_the_mongo_store_writes(
    mongo: tuple[MongoStore, FakeCollection, FakeClient],
) -> None:
    store, collection, _ = mongo
    assert await store.insert("articles", []) == []
    assert await store.insert("articles", [{"title": "One", "_id": None}]) == ["one"]
    assert "_id" not in collection.seen["insert_one"]
    assert await store.insert("articles", [{"title": "One"}, {"title": "Two"}]) == ["a", "b"]

    assert await store.update(Query("articles"), {}) == 0
    assert await store.update(Query("articles"), {"views": 1}) == 2
    assert collection.seen["update_many"][1] == {"$set": {"views": 1}}

    assert await store.increment(Query("articles"), {"views": 1}, {}) == 2
    assert collection.seen["update_many"][1] == {"$inc": {"views": 1}}
    assert await store.increment(Query("articles"), {"views": 1}, {"seen": True}) == 2
    assert collection.seen["update_many"][1]["$set"] == {"seen": True}

    assert await store.delete(Query("articles")) == 4


async def test_the_mongo_store_manages_collections(
    mongo: tuple[MongoStore, FakeCollection, FakeClient],
) -> None:
    store, collection, client = mongo
    assert await store.create_index("articles", [("slug", 1)], unique=True, name="slug") == "made"
    assert collection.seen["create_index"] == ([("slug", 1)], {"unique": True, "name": "slug"})
    assert await store.create_index("articles", [("slug", 1)]) == "made"

    assert await store.indexes("articles") == [
        {"name": "slug_1", "keys": [("slug", 1)], "unique": True}
    ]

    await store.drop_collection("articles")
    assert client.database.dropped == ["articles"]
    assert await store.collections() == ["a", "b"]

    await store.disconnect()
    assert client.closed is True
    await store.disconnect()


async def test_a_find_without_order_or_window_asks_for_everything(
    mongo: tuple[MongoStore, FakeCollection, FakeClient],
) -> None:
    store, collection, _ = mongo
    assert await store.find(Query("articles")) == [{"_id": 1, "title": "Notes"}]
    assert collection.seen["find"] == ({}, None)
    assert await store.count(Query("articles")) == 7
    assert collection.seen["count"][1] == {}


def test_a_store_without_a_client_builds_one_lazily(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys
    import types

    built: dict[str, Any] = {}

    class FakeMotorClient:
        def __init__(self, dsn: str, **options: Any) -> None:
            built["dsn"] = dsn
            built["options"] = options

    module = types.ModuleType("motor.motor_asyncio")
    module.AsyncIOMotorClient = FakeMotorClient  # type: ignore[attr-defined]
    package = types.ModuleType("motor")
    monkeypatch.setitem(sys.modules, "motor", package)
    monkeypatch.setitem(sys.modules, "motor.motor_asyncio", module)

    store = MongoStore("mongo", {"host": "db", "port": 1, "options": {"tz_aware": True}})
    assert "MongoStore" in repr(store)
    assert isinstance(store.client, FakeMotorClient)
    assert store.client is store.client
    assert built == {"dsn": "mongodb://db:1", "options": {"tz_aware": True}}


def test_a_missing_motor_is_named_rather_than_imploding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    real_import = builtins.__import__

    def refuse(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith("motor"):
            raise ImportError("no motor here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)
    with pytest.raises(MongoNotInstalled):
        MongoStore("mongo", {}).client


# --- the manager ------------------------------------------------------------


async def test_the_manager_tells_stores_and_databases_apart(
    documents: DatabaseManager,
) -> None:
    assert documents.is_document("docs") is True
    assert documents.is_document("sqlite") is False
    assert documents.driver("mongo") == "mongodb"
    assert documents.document_connection_names() == ["docs", "mongo", "second"]

    assert isinstance(documents.store("docs"), MemoryStore)
    assert isinstance(documents.store("mongo"), MongoStore)
    assert documents.store("docs") is documents.store("docs")

    with pytest.raises(ConnectionError_, match="is a document store"):
        documents.connection("docs")
    with pytest.raises(ConnectionError_, match="not a document store"):
        documents.store("sqlite")
    with pytest.raises(ConnectionError_, match="is not configured"):
        documents.store("nowhere")


async def test_a_store_can_be_handed_in_and_replaced(documents: DatabaseManager) -> None:
    store = MemoryStore("stub")
    documents.set_store("docs", store)
    assert documents.store("docs") is store

    documents.add_connection("docs", {"driver": "memory"})
    assert documents.store("docs") is not store


async def test_disconnecting_forgets_the_stores(documents: DatabaseManager) -> None:
    documents.store("docs")
    await documents.disconnect("docs")
    await documents.disconnect("sqlite")
    documents.store("docs")
    await documents.disconnect()
    assert documents._stores == {}
