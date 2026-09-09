"""M27 search — the Searchable mixin, the builder, and the engines."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from almasix.orm import Schema
from almasix.orm.collection import Collection
from almasix.orm.model import Model
from almasix.orm.soft_deletes import SoftDeletes
from almasix.scout import (
    CollectionEngine,
    DatabaseEngine,
    Engine,
    EngineManager,
    MakeSearchable,
    MeilisearchEngine,
    NullEngine,
    RemoveFromSearch,
    Scout,
    Searchable,
    SearchException,
    UnsupportedEngineException,
    flush_search,
    get_engine_manager,
    set_engine_manager,
)
from almasix.scout.engines.database import full_text_clause
from tests.orm_support import memory_db  # noqa: F401

pytestmark = pytest.mark.anyio


# --- the models under test ------------------------------------------------


class Post(Searchable, Model):
    table = "posts"
    timestamps = False
    searchable_columns = ("title", "body")

    def to_searchable_array(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "body": self.body}


class Draftable(Searchable, Model):
    table = "drafts"
    timestamps = False
    searchable_columns = ("title",)

    def should_be_searchable(self) -> bool:
        return bool(self.published)

    def search_index_should_be_updated(self) -> bool:
        return self.was_changed("title") or not self.get_original("id")


class Note(SoftDeletes, Searchable, Model):
    table = "notes"
    timestamps = False
    searchable_columns = ("body",)

    def to_searchable_array(self) -> dict[str, Any]:
        return {"id": self.id, "body": self.body}


async def schema() -> None:
    await Schema.create(
        "posts",
        lambda t: (
            t.id(),
            t.string("title"),
            t.text("body").nullable(),
            t.integer("author_id").nullable(),
        ),
    )
    await Schema.create(
        "drafts",
        lambda t: (t.id(), t.string("title"), t.boolean("published").default(False)),
    )
    await Schema.create(
        "notes",
        lambda t: (t.id(), t.string("body"), t.timestamp("deleted_at").nullable()),
    )


@pytest.fixture
async def posts(memory_db: Any) -> AsyncIterator[list[Post]]:
    del memory_db
    await schema()
    rows = [
        await Post.force_create(
            {"title": "Almasix ships search", "body": "Scout parity", "author_id": 1}
        ),
        await Post.force_create(
            {"title": "Broadcasting", "body": "websockets and pusher", "author_id": 1}
        ),
        await Post.force_create({"title": "Documents", "body": "mongo and memory", "author_id": 2}),
    ]
    yield rows


@pytest.fixture(autouse=True)
def fresh_manager() -> AsyncIterator[EngineManager]:
    """Every test gets its own configuration; none inherits an engine."""
    manager = EngineManager(config={"driver": "collection"})
    set_engine_manager(manager)
    yield manager
    set_engine_manager(None)
    Scout.set_manager(None)


# --- the manager ------------------------------------------------------------


def test_the_manager_resolves_every_engine_it_ships(fresh_manager: EngineManager) -> None:
    assert isinstance(fresh_manager.engine("collection"), CollectionEngine)
    assert isinstance(fresh_manager.engine("database"), DatabaseEngine)
    assert isinstance(fresh_manager.engine("meilisearch"), MeilisearchEngine)
    assert isinstance(fresh_manager.engine("null"), NullEngine)


def test_an_engine_is_resolved_once(fresh_manager: EngineManager) -> None:
    assert fresh_manager.engine() is fresh_manager.engine("collection")
    fresh_manager.forget_engine("collection")
    assert fresh_manager.engine("collection") is not None
    fresh_manager.forget_engine()
    assert fresh_manager._engines == {}


def test_an_unknown_engine_says_so_and_names_the_alternatives(
    fresh_manager: EngineManager,
) -> None:
    with pytest.raises(UnsupportedEngineException) as failure:
        fresh_manager.engine("elasticsearch")
    assert "meilisearch" in str(failure.value)
    assert "Scout.extend()" in str(failure.value)


def test_an_application_can_bring_its_own_engine(fresh_manager: EngineManager) -> None:
    class MySql(NullEngine):
        driver = "mysql"

    fresh_manager.extend("mysql", lambda app, config, name: MySql(name, config))
    fresh_manager.set_default_driver("mysql")
    assert isinstance(Scout.engine(), MySql)
    assert Scout.driver() == "mysql"


def test_the_manager_reads_what_search_is_configured_to_do() -> None:
    manager = EngineManager(
        config={
            "driver": "null",
            "prefix": "test_",
            "queue": {"connection": "redis", "queue": "scout"},
            "after_commit": True,
            "soft_delete": True,
            "chunk": {"searchable": 25},
        }
    )
    assert manager.prefix == "test_"
    assert manager.queues is True
    assert manager.queue_options == {"connection": "redis", "queue": "scout"}
    assert manager.after_commit is True
    assert manager.soft_delete is True
    assert manager.chunk_size() == 25
    assert manager.chunk_size("unsearchable") == 500


def test_without_configuration_search_still_works() -> None:
    set_engine_manager(None)
    manager = get_engine_manager()
    assert manager.get_default_driver() == "database"
    assert get_engine_manager() is manager


# --- the searchable model ---------------------------------------------------


async def test_a_model_says_where_it_is_indexed_and_how(posts: list[Post]) -> None:
    assert Post.searchable_as() == "posts"
    assert Post.get_scout_key_name() == "id"
    assert posts[0].get_scout_key() == posts[0].id
    assert posts[0].to_searchable_array()["title"] == "Almasix ships search"
    assert posts[0].scout_metadata() == {}
    assert posts[0].should_be_searchable() is True
    assert posts[0].search_index_should_be_updated() is True


def test_the_prefix_moves_the_index(fresh_manager: EngineManager) -> None:
    fresh_manager.config["prefix"] = "staging_"
    assert Post.searchable_as() == "staging_posts"


async def test_searching_finds_what_the_phrase_is_in(posts: list[Post]) -> None:
    found = await Post.search("pusher").get()
    assert [post.title for post in found] == ["Broadcasting"]


async def test_an_empty_phrase_finds_everything(posts: list[Post]) -> None:
    found = await Post.search().get()
    assert len(found) == len(posts)


async def test_a_search_can_be_filtered_ordered_and_cut_short(posts: list[Post]) -> None:
    found = await Post.search("").where("author_id", 1).order_by("title").take(1).get()
    assert [post.title for post in found] == ["Almasix ships search"]

    both = await Post.search("").where_in("author_id", [1, 2]).order_by("id", "desc").get()
    assert [post.id for post in both] == [3, 2, 1]

    rest = await Post.search("").where_not_in("author_id", [1]).get()
    assert [post.title for post in rest] == ["Documents"]


async def test_a_search_answers_keys_counts_and_a_first_hit(posts: list[Post]) -> None:
    assert await Post.search("mongo").keys() == [3]
    assert await Post.search("").count() == 3
    first = await Post.search("Almasix").first()
    assert first.title == "Almasix ships search"
    assert await Post.search("nothing at all").first() is None


async def test_a_search_streams_and_paginates(posts: list[Post]) -> None:
    streamed = [post.id async for post in Post.search("").cursor()]
    assert sorted(streamed) == [1, 2, 3]

    page = await Post.search("").paginate(per_page=2, page=1)
    assert page.total == 3
    assert page.last_page == 2
    assert len(page.items) == 2

    second = await Post.search("").simple_paginate(per_page=2, page=2)
    assert second.has_more_pages() is False
    assert len(second.items) == 1

    raw = await Post.search("").paginate_raw(per_page=2, page=1)
    assert raw["total"] == 3
    simple_raw = await Post.search("").simple_paginate_raw(per_page=2, page=1)
    assert len(simple_raw["models"]) == 2


async def test_the_query_behind_the_results_can_be_shaped(posts: list[Post]) -> None:
    found = await Post.search("").query_using(lambda query: query.where("author_id", "=", 2)).get()
    assert [post.title for post in found] == ["Documents"]


async def test_a_search_can_be_built_conditionally(posts: list[Post]) -> None:
    builder = (
        Post.search("")
        .when(True, lambda search, _: search.where("author_id", 2))
        .unless(True, lambda search, _: search.take(1))
        .when(False, lambda search, _: search.take(99), lambda search, _: search.order_by("id"))
        .tap(lambda search: search.options({"hitsPerPage": 5}))
    )
    assert builder.wheres == {"author_id": 2}
    assert builder.limit is None
    assert builder.orders == [{"column": "id", "direction": "asc"}]
    assert builder.search_options == {"hitsPerPage": 5}
    assert (await builder.get()).count() == 1


def test_latest_and_oldest_use_the_timestamp_column() -> None:
    assert Post.search("").latest().orders == [{"column": "created_at", "direction": "desc"}]
    assert Post.search("").oldest("id").orders == [{"column": "id", "direction": "asc"}]


def test_a_search_can_be_pointed_at_another_index() -> None:
    assert Post.search("x").within("posts_by_rank").index == "posts_by_rank"


# --- keeping the index in step ---------------------------------------------


async def test_saving_a_model_indexes_it(posts: list[Post]) -> None:
    fake = Scout.fake()
    post = await Post.force_create({"title": "Search", "body": "scout"})
    fake.assert_synced(post)
    assert fake.written("update")[0].documents[0]["title"] == "Search"


async def test_deleting_a_model_removes_it(posts: list[Post]) -> None:
    fake = Scout.fake()
    await posts[0].delete()
    fake.assert_removed(posts[0])


async def test_a_model_that_should_not_be_searchable_is_taken_out(memory_db: Any) -> None:
    del memory_db
    await schema()
    fake = Scout.fake()

    draft = await Draftable.force_create({"title": "Hidden", "published": False})
    fake.assert_removed(draft)

    draft.published = True
    draft.title = "Published"
    await draft.save()
    fake.assert_synced(draft)


async def test_a_write_that_changes_nothing_worth_indexing_is_skipped(memory_db: Any) -> None:
    del memory_db
    await schema()

    class Quiet(Searchable, Model):
        table = "drafts"
        timestamps = False

        def search_index_should_be_updated(self) -> bool:
            return False

    fake = Scout.fake()
    quiet = await Quiet.force_create({"title": "Kept", "published": True})
    quiet.title = "Renamed"
    await quiet.save()
    fake.assert_nothing_synced()


async def test_indexing_can_be_paused(posts: list[Post]) -> None:
    fake = Scout.fake()
    with Post.without_syncing_to_search():
        await Post.force_create({"title": "Quiet", "body": "not indexed"})
    fake.assert_nothing_synced()

    Post.disable_search_syncing()
    await Post.force_create({"title": "Also quiet", "body": ""})
    fake.assert_nothing_synced()
    Post.enable_search_syncing()

    await Post.force_create({"title": "Loud", "body": ""})
    assert fake.written("update")


async def test_a_whole_query_and_a_collection_can_be_indexed(posts: list[Post]) -> None:
    fake = Scout.fake()
    indexed = await Post.query().where("author_id", "=", 1).searchable()
    assert indexed == 2
    fake.assert_synced(Post, [1, 2])

    removed = await Post.query().unsearchable()
    assert removed == 3

    fake.flush_records()
    await (await Post.all()).searchable()
    fake.assert_synced(Post, [1, 2, 3])
    await (await Post.all()).unsearchable()
    fake.assert_removed(Post, [1, 2, 3])


async def test_indexing_a_query_of_something_unsearchable_says_so(memory_db: Any) -> None:
    del memory_db
    await schema()

    class Plain(Model):
        table = "posts"
        timestamps = False

    with pytest.raises(TypeError, match="not searchable"):
        await Plain.query().searchable()
    with pytest.raises(TypeError, match="not searchable"):
        await Plain.query().unsearchable()
    with pytest.raises(TypeError, match="not searchable"):
        await Collection([Plain()]).searchable()
    with pytest.raises(TypeError, match="not searchable"):
        await Collection([Plain()]).unsearchable()


async def test_an_empty_collection_indexes_nothing(posts: list[Post]) -> None:
    fake = Scout.fake()
    await Collection([]).searchable()
    await Collection([]).unsearchable()
    fake.assert_nothing_synced()


async def test_importing_and_flushing_a_whole_model(posts: list[Post]) -> None:
    fake = Scout.fake()
    assert await Post.make_all_searchable() == 3
    fake.assert_synced(Post, [1, 2, 3])

    await Post.remove_all_from_search()
    fake.assert_flushed(Post)


async def test_an_import_can_be_shaped_and_filtered(memory_db: Any) -> None:
    del memory_db
    await schema()
    await Draftable.force_create({"title": "One", "published": True})
    await Draftable.force_create({"title": "Two", "published": False})

    seen: list[Any] = []

    class Shaped(Draftable):
        table = "drafts"

        @classmethod
        def make_all_searchable_using(cls, query: Any) -> Any:
            seen.append(query)
            return query

        @classmethod
        def make_searchable_using(cls, models: Any) -> Any:
            return models

    fake = Scout.fake()
    assert await Shaped.make_all_searchable(chunk=1) == 1
    assert len(seen) == 1
    assert fake.written("update")[0].keys == [1]


# --- soft deletes -----------------------------------------------------------


async def test_a_trashed_row_leaves_the_index_by_default(memory_db: Any) -> None:
    del memory_db
    await schema()
    note = await Note.force_create({"body": "temporary"})

    fake = Scout.fake()
    await note.delete()
    fake.assert_removed(note)


async def test_a_trashed_row_can_stay_in_the_index_flagged(
    memory_db: Any,
    fresh_manager: EngineManager,
) -> None:
    del memory_db
    fresh_manager.config["soft_delete"] = True
    await schema()
    note = await Note.force_create({"body": "kept"})
    assert note.scout_metadata() == {"__soft_deleted": 0}

    fake = Scout.fake()
    await note.delete()
    assert fake.written("update")[-1].documents[0]["__soft_deleted"] == 1

    await note.restore()
    assert fake.written("update")[-1].documents[0]["__soft_deleted"] == 0


async def test_trashed_rows_are_searchable_when_they_are_indexed(
    memory_db: Any,
    fresh_manager: EngineManager,
) -> None:
    del memory_db
    fresh_manager.config["soft_delete"] = True
    await schema()
    kept = await Note.force_create({"body": "kept"})
    gone = await Note.force_create({"body": "gone"})
    await gone.delete()

    assert [note.id for note in await Note.search("").get()] == [kept.id]
    assert [note.id for note in await Note.search("").with_trashed().get()] == [gone.id, kept.id]
    assert [note.id for note in await Note.search("").only_trashed().get()] == [gone.id]


# --- the database engine ----------------------------------------------------


async def test_the_database_engine_searches_in_sql(
    posts: list[Post],
    fresh_manager: EngineManager,
) -> None:
    fresh_manager.set_default_driver("database")
    found = await Post.search("pusher").get()
    assert [post.title for post in found] == ["Broadcasting"]

    assert await Post.search("").count() == 3
    page = await Post.search("").paginate(per_page=2)
    assert page.total == 3 and len(page.items) == 2


async def test_the_database_engine_takes_the_query_callback_as_a_filter(
    posts: list[Post],
    fresh_manager: EngineManager,
) -> None:
    fresh_manager.set_default_driver("database")
    found = await Post.search("").query_using(lambda query: query.where("author_id", "=", 2)).get()
    assert [post.title for post in found] == ["Documents"]


async def test_the_database_engine_matches_a_prefix_when_told_to(
    memory_db: Any,
    fresh_manager: EngineManager,
) -> None:
    del memory_db
    fresh_manager.set_default_driver("database")
    await schema()

    class Prefixed(Post):
        table = "posts"
        searchable_columns = ("title",)
        search_using_prefix = ("title",)

    await Prefixed.force_create({"title": "Almasix", "body": ""})
    await Prefixed.force_create({"title": "An Almasix release", "body": ""})

    found = await Prefixed.search("Almasix").get()
    assert [post.title for post in found] == ["Almasix"]


async def test_the_database_engine_orders_filters_and_limits(
    posts: list[Post],
    fresh_manager: EngineManager,
) -> None:
    fresh_manager.set_default_driver("database")
    found = await (
        Post.search("")
        .where("author_id", 1)
        .where_in("id", [1, 2, 3])
        .where_not_in("id", [2])
        .order_by("title")
        .take(5)
        .get()
    )
    assert [post.title for post in found] == ["Almasix ships search"]


async def test_the_database_engine_honours_trashed_searches(
    memory_db: Any,
    fresh_manager: EngineManager,
) -> None:
    del memory_db
    fresh_manager.config.update({"driver": "database", "soft_delete": True})
    await schema()
    kept = await Note.force_create({"body": "kept"})
    gone = await Note.force_create({"body": "gone"})
    await gone.delete()

    assert [note.id for note in await Note.search("").get()] == [kept.id]
    assert [note.id for note in await Note.search("").only_trashed().get()] == [gone.id]
    assert len(await Note.search("").with_trashed().get()) == 2


async def test_the_database_engine_needs_columns_to_search(
    memory_db: Any,
    fresh_manager: EngineManager,
) -> None:
    del memory_db
    fresh_manager.set_default_driver("database")
    await schema()

    class Columnless(Searchable, Model):
        table = "posts"
        timestamps = False

        def to_searchable_array(self) -> dict[str, Any]:
            return {}

    with pytest.raises(ValueError, match="no searchable columns"):
        await Columnless.search("x").get()


async def test_the_database_engine_falls_back_to_the_searchable_array(
    posts: list[Post],
    fresh_manager: EngineManager,
) -> None:
    fresh_manager.set_default_driver("database")

    class Declared(Post):
        table = "posts"
        searchable_columns = ()

        def to_searchable_array(self) -> dict[str, Any]:
            return {"title": self.get_attribute("title")}

    found = await Declared.search("Broadcasting").get()
    assert [post.title for post in found] == ["Broadcasting"]

    class Unanswerable(Post):
        table = "posts"
        searchable_columns = ()

    with pytest.raises(ValueError, match="no searchable columns"):
        await Unanswerable.search("Broadcasting").get()


def test_full_text_is_spelled_the_way_the_dialect_spells_it() -> None:
    assert "to_tsvector" in full_text_clause("postgresql", "posts", ["body"])
    assert "MATCH (posts.body)" in full_text_clause("mysql", "posts", ["body"])


async def test_the_database_engine_indexes_nothing(posts: list[Post]) -> None:
    engine = DatabaseEngine("database")
    assert await engine.update(posts) is None
    assert await engine.delete(posts) is None
    assert await engine.flush(Post) is None


# --- the null engine --------------------------------------------------------


async def test_the_null_engine_finds_nothing(
    posts: list[Post], fresh_manager: EngineManager
) -> None:
    fresh_manager.set_default_driver("null")
    assert len(await Post.search("Almasix").get()) == 0
    assert await Post.search("Almasix").count() == 0
    assert await Post.search("Almasix").keys() == []
    assert len(await Post.search("Almasix").paginate()) == 0

    engine = NullEngine("null")
    assert await engine.update(posts) is None
    assert await engine.delete(posts) is None
    assert await engine.flush(Post) is None


# --- the queue --------------------------------------------------------------


async def test_indexing_can_go_through_the_queue(
    posts: list[Post],
    fresh_manager: EngineManager,
) -> None:
    fresh_manager.config["queue"] = {"connection": "redis", "queue": "scout"}
    dispatched: list[Any] = []

    async def capture(job: Any) -> Any:
        dispatched.append(job)
        return job

    import almasix.queue.helpers as queue_helpers

    original = queue_helpers.dispatch
    queue_helpers.dispatch = capture
    try:
        await posts[0].searchable()
        await posts[1].unsearchable()
    finally:
        queue_helpers.dispatch = original

    assert isinstance(dispatched[0], MakeSearchable)
    assert dispatched[0].keys == [posts[0].id]
    assert dispatched[0].queue == "scout"
    assert dispatched[0].connection == "redis"
    assert isinstance(dispatched[1], RemoveFromSearch)


async def test_a_queued_index_write_does_the_work_when_it_runs(posts: list[Post]) -> None:
    fake = Scout.fake()
    job = MakeSearchable.for_models([posts[0]])
    assert "Post" in repr(job)
    await job.handle()
    fake.assert_synced(Post, [posts[0].id])

    removal = RemoveFromSearch.for_models([posts[0]])
    await removal.handle()
    fake.assert_removed(Post, [posts[0].id])


async def test_a_queued_write_skips_what_should_not_be_indexed(memory_db: Any) -> None:
    del memory_db
    await schema()
    draft = await Draftable.force_create({"title": "Hidden", "published": False})

    fake = Scout.fake()
    await MakeSearchable.for_models([draft]).handle()
    fake.assert_nothing_synced()


async def test_without_a_queue_the_write_happens_anyway(
    posts: list[Post],
    fresh_manager: EngineManager,
) -> None:
    """A missing queue connection must not cost the application its index."""
    fresh_manager.config["queue"] = True
    fake = Scout.fake()
    await posts[0].searchable()
    fake.assert_synced(posts[0])


# --- after commit -----------------------------------------------------------


async def test_indexing_can_wait_for_the_transaction(
    posts: list[Post],
    fresh_manager: EngineManager,
    memory_db: Any,
) -> None:
    fresh_manager.config["after_commit"] = True
    fake = Scout.fake()

    connection = memory_db.connection()
    async with connection.transaction():
        await Post.force_create({"title": "Deferred", "body": ""})
        fake.assert_nothing_synced()

    await flush_search()
    assert fake.written("update")[0].documents[0]["title"] == "Deferred"


async def test_without_a_transaction_a_deferred_index_write_happens_now(
    posts: list[Post],
    fresh_manager: EngineManager,
) -> None:
    fresh_manager.config["after_commit"] = True
    fake = Scout.fake()
    await Post.force_create({"title": "Immediate", "body": ""})
    fake.assert_synced(Post, [4])


async def test_a_model_without_a_database_still_indexes(fresh_manager: EngineManager) -> None:
    from almasix.orm.facade import set_manager

    fresh_manager.config["after_commit"] = True
    set_manager(None)

    from almasix.scout.pending import defer_until_commit

    assert defer_until_commit(Post(), lambda: None) is False


# --- the fake ---------------------------------------------------------------


async def test_the_fake_answers_searches_with_what_it_was_given(posts: list[Post]) -> None:
    fake = Scout.fake([posts[2]])
    found = await Post.search("anything").get()
    assert [post.title for post in found] == ["Documents"]
    fake.assert_searched("anything")
    fake.assert_search_count(1)

    fake.returns(posts)
    page = await Post.search("").paginate(per_page=2, page=2)
    assert len(page.items) == 1
    assert page.total == 3
    assert await Post.search("").keys() == [1, 2, 3]


async def test_the_fake_complains_when_the_index_was_not_touched(posts: list[Post]) -> None:
    fake = Scout.fake()
    with pytest.raises(AssertionError, match="Nothing was indexed"):
        fake.assert_synced(Post)
    with pytest.raises(AssertionError, match="Nothing was removed"):
        fake.assert_removed(Post)
    with pytest.raises(AssertionError, match="was not flushed"):
        fake.assert_flushed(Post)
    with pytest.raises(AssertionError, match="No search for"):
        fake.assert_searched("nothing")

    await posts[0].searchable()
    with pytest.raises(AssertionError, match="Expected no index writes"):
        fake.assert_nothing_synced()
    with pytest.raises(AssertionError, match="Expected 3 searches"):
        fake.assert_search_count(3)
    with pytest.raises(AssertionError, match="with keys"):
        fake.assert_synced(Post, [99])


async def test_the_fake_records_index_management(posts: list[Post]) -> None:
    fake = Scout.fake()
    await fake.create_index("posts", {"primaryKey": "uuid"})
    assert fake.indexes == ["posts"]
    await fake.delete_index("posts")
    await fake.sync_settings(Post)
    await fake.delete_all_indexes()
    assert fake.indexes == []
    assert {write.action for write in fake.writes} == {
        "create-index",
        "delete-index",
        "settings",
        "delete-all-indexes",
    }
    assert fake.written("create-index")[0].payload == {"primaryKey": "uuid"}

    await fake.update([])
    await fake.delete([])
    assert len(fake.writes) == 4


# --- meilisearch ------------------------------------------------------------


@pytest.fixture
def meili(fresh_manager: EngineManager) -> MeilisearchEngine:
    fresh_manager.config.update(
        {
            "driver": "meilisearch",
            "meilisearch": {"host": "http://meili.test:7700", "key": "masterKey"},
        }
    )
    return fresh_manager.engine("meilisearch")  # type: ignore[return-value]


@pytest.fixture
def faked_http() -> AsyncIterator[None]:
    from almasix.client.facade import set_factory

    set_factory(None)
    yield
    set_factory(None)


async def test_meilisearch_indexes_and_deletes_documents(
    posts: list[Post],
    meili: MeilisearchEngine,
    faked_http: None,
) -> None:
    from almasix.client.facade import Http

    Http.fake({"*": Http.response({"taskUid": 1})})

    await meili.update(posts)
    await meili.delete([posts[0]])
    await meili.flush(Post)
    await meili.update([])
    await meili.delete([])

    Http.assert_sent_count(3)
    Http.assert_sent(
        lambda request: (
            request.url.endswith("/indexes/posts/documents?primaryKey=id")
            and request.method == "PUT"
            and request.data[0]["title"] == "Almasix ships search"
        )
    )
    Http.assert_sent(
        lambda request: (
            request.url.endswith("/indexes/posts/documents/delete-batch") and request.data == [1]
        )
    )
    Http.assert_sent(
        lambda request: (
            request.method == "DELETE" and request.url.endswith("/indexes/posts/documents")
        )
    )


async def test_meilisearch_searches_with_filters_and_sorting(
    posts: list[Post],
    meili: MeilisearchEngine,
    faked_http: None,
) -> None:
    from almasix.client.facade import Http

    Http.fake(
        {
            "*": Http.response(
                {"hits": [{"id": 2, "title": "Broadcasting"}], "estimatedTotalHits": 1}
            )
        }
    )

    found = await (
        Post.search("pusher")
        .where("author_id", 1)
        .where_in("id", [1, 2])
        .where_not_in("id", [3])
        .order_by("id", "desc")
        .take(10)
        .options({"attributesToHighlight": ["title"]})
        .get()
    )
    assert [post.title for post in found] == ["Broadcasting"]

    Http.assert_sent(
        lambda request: (
            request.url.endswith("/indexes/posts/search")
            and request.data["q"] == "pusher"
            and request.data["filter"] == "author_id = 1 AND id IN [1, 2] AND id NOT IN [3]"
            and request.data["sort"] == ["id:desc"]
            and request.data["limit"] == 10
            and request.data["attributesToHighlight"] == ["title"]
        )
    )


async def test_meilisearch_paginates_and_counts(
    posts: list[Post],
    meili: MeilisearchEngine,
    faked_http: None,
) -> None:
    from almasix.client.facade import Http

    Http.fake(
        {"*": Http.response({"hits": [{"id": 1, "title": "Almasix ships search"}], "totalHits": 9})}
    )

    page = await Post.search("almasix").paginate(per_page=1, page=2)
    assert page.total == 9
    assert [post.id for post in page.items] == [1]
    Http.assert_sent(lambda request: request.data["hitsPerPage"] == 1 and request.data["page"] == 2)


def test_meilisearch_reads_the_totals_and_keys_it_is_given(meili: MeilisearchEngine) -> None:
    assert meili.map_ids({"hits": []}) == []
    assert meili.map_ids({"hits": [{"uuid": "a"}, {"uuid": "b"}]}) == ["a", "b"]
    assert meili.total_count({"hits": [], "nbHits": 4}) == 4
    assert meili.total_count({"hits": [{"id": 1}]}) == 1


async def test_meilisearch_manages_indexes_and_settings(
    meili: MeilisearchEngine,
    faked_http: None,
    fresh_manager: EngineManager,
) -> None:
    from almasix.client.facade import Http

    Http.fake(
        {
            "*/indexes?limit=1000": Http.response({"results": [{"uid": "posts"}]}),
            "*": Http.response({"taskUid": 2}),
        }
    )

    await meili.create_index("posts", {"primaryKey": "id"})
    await meili.delete_index("posts")
    await meili.delete_all_indexes()

    Http.assert_sent(
        lambda request: (
            request.method == "POST"
            and request.url.endswith("/indexes")
            and request.data == {"uid": "posts", "primaryKey": "id"}
        )
    )
    Http.assert_sent(lambda request: request.method == "DELETE")

    assert await meili.sync_settings(Post) is False

    meili.config["index-settings"] = {"posts": {"filterableAttributes": ["author_id"]}}
    assert await meili.sync_settings(Post) is True
    Http.assert_sent(
        lambda request: (
            request.method == "PATCH" and request.data == {"filterableAttributes": ["author_id"]}
        )
    )


async def test_meilisearch_settings_may_be_keyed_by_the_model_itself(
    meili: MeilisearchEngine,
    faked_http: None,
) -> None:
    from almasix.client.facade import Http

    Http.fake({"*": Http.response({"taskUid": 3})})
    meili.config["index-settings"] = {Post: {"sortableAttributes": ["id"]}}
    assert await meili.sync_settings(Post) is True

    meili.config["index-settings"] = {"Post": {"sortableAttributes": ["id"]}}
    assert await meili.sync_settings(Post) is True

    meili.config["index-settings"] = {"other_index": {}}
    assert await meili.sync_settings(Post) is False


async def test_meilisearch_adds_soft_deletes_to_the_filterable_attributes(
    meili: MeilisearchEngine,
    faked_http: None,
    fresh_manager: EngineManager,
) -> None:
    from almasix.client.facade import Http

    Http.fake({"*": Http.response({"taskUid": 4})})
    fresh_manager.config["soft_delete"] = True
    meili.config["index-settings"] = {"notes": {"filterableAttributes": ["body"]}}

    assert await meili.sync_settings(Note) is True
    Http.assert_sent(
        lambda request: request.data["filterableAttributes"] == ["body", "__soft_deleted"]
    )

    # Asking twice must not add the flag twice.
    meili.config["index-settings"] = {"notes": {"filterableAttributes": ["body", "__soft_deleted"]}}
    assert await meili.sync_settings(Note) is True


async def test_meilisearch_says_what_the_service_said_when_it_refuses(
    posts: list[Post],
    meili: MeilisearchEngine,
    faked_http: None,
) -> None:
    from almasix.client.facade import Http

    Http.fake({"*": Http.response({"message": "index not found"}, status=404)})

    with pytest.raises(SearchException, match="Meilisearch answered 404"):
        await meili.update(posts)


async def test_meilisearch_hands_the_search_to_a_callback_when_given_one(
    posts: list[Post],
    meili: MeilisearchEngine,
) -> None:
    seen: list[Any] = []

    def customize(engine: Any, query: str, payload: dict[str, Any]) -> Any:
        seen.append((engine, query, payload))
        return {"hits": [{"id": 3}], "estimatedTotalHits": 1}

    found = await Post.search("mongo", customize).get()
    assert [post.title for post in found] == ["Documents"]
    assert seen[0][1] == "mongo"

    async def customize_async(engine: Any, query: str, payload: dict[str, Any]) -> Any:
        return {"hits": [{"id": 1}], "estimatedTotalHits": 1}

    found = await Post.search("mongo", customize_async).get()
    assert [post.id for post in found] == [1]


def test_meilisearch_reads_its_host_and_key(fresh_manager: EngineManager) -> None:
    bare = MeilisearchEngine("meilisearch", {})
    assert bare.host == "http://localhost:7700"
    assert bare.key is None

    configured = MeilisearchEngine("meilisearch", {"host": "http://search:7700/", "key": "k"})
    assert configured.host == "http://search:7700"
    assert configured.key == "k"


def test_meilisearch_quotes_the_values_it_filters_on() -> None:
    from almasix.scout.engines.meilisearch import _literal

    assert _literal(True) == "true"
    assert _literal(False) == "false"
    assert _literal(3) == "3"
    assert _literal('a "quoted" word') == '"a \\"quoted\\" word"'


# --- the contract ------------------------------------------------------------


def test_the_engine_contract_has_defaults_a_simple_engine_can_keep() -> None:
    class Minimal(Engine):
        driver = "minimal"

        async def update(self, models: Any) -> None: ...
        async def delete(self, models: Any) -> None: ...
        async def flush(self, model: Any) -> None: ...
        async def search(self, builder: Any) -> Any:
            return {}

        async def paginate(self, builder: Any, per_page: int, page: int) -> Any:
            return {}

        def map_ids(self, results: Any) -> list[Any]:
            return []

        def total_count(self, results: Any) -> int:
            return 0

    engine = Minimal()
    assert engine.name == "minimal"
    assert repr(engine) == "Minimal('minimal')"


async def test_the_engine_contract_defaults_do_nothing_loudly() -> None:
    engine = NullEngine("null")
    assert await engine.create_index("posts") is None
    assert await engine.delete_index("posts") is None
    assert await engine.delete_all_indexes() is None
    assert await engine.sync_settings(Post) is False


async def test_hydration_keeps_the_order_the_engine_ranked(posts: list[Post]) -> None:
    from almasix.scout.engines.base import hydrate

    builder = Post.search("")
    assert len(await hydrate(builder, [])) == 0
    ordered = await hydrate(builder, [3, 1])
    assert [post.id for post in ordered] == [3, 1]
    # A key the database no longer has is simply not there.
    assert [post.id for post in await hydrate(builder, [3, 99])] == [3]


def test_a_search_builder_says_what_it_is() -> None:
    assert "Post 'almasix'" in repr(Post.search("almasix"))


# --- the façade ---------------------------------------------------------------


def test_the_facade_reaches_for_the_manager_the_application_configured(
    fresh_manager: EngineManager,
) -> None:
    Scout.set_manager(None)
    assert Scout.manager() is fresh_manager
    assert Scout.driver() == "collection"

    Scout.extend("shouty", lambda app, config, name: NullEngine(name, config))
    Scout.use("shouty")
    assert isinstance(Scout.engine(), NullEngine)

    Scout.forget_engine("shouty")
    assert fresh_manager._engines == {}
    Scout.use("collection")


# --- the provider ---------------------------------------------------------------


def test_the_provider_binds_the_manager_and_teaches_queries_to_index(tmp_path: Any) -> None:
    from almasix.framework.application import Application
    from almasix.orm.builder import QueryBuilder
    from almasix.scout.provider import ScoutServiceProvider

    app = Application(base_path=tmp_path)
    app.config.set("scout", {"driver": "null", "prefix": "test_"})
    provider = ScoutServiceProvider(app)
    provider.register()
    provider.boot()

    manager = app.make(EngineManager)
    assert manager is app.make("scout")
    assert manager.get_default_driver() == "null"
    assert get_engine_manager() is manager
    assert Scout.manager() is manager
    assert hasattr(QueryBuilder, "searchable")


def test_the_provider_falls_back_to_the_default_configuration(tmp_path: Any) -> None:
    from almasix.framework.application import Application
    from almasix.scout.provider import ScoutServiceProvider

    app = Application(base_path=tmp_path)
    app.config.set("scout", {})
    provider = ScoutServiceProvider(app)
    provider.register()
    provider.boot()

    assert app.make(EngineManager).get_default_driver() == "database"


def test_the_provider_does_nothing_when_nothing_is_bound(tmp_path: Any) -> None:
    from almasix.framework.application import Application
    from almasix.scout.provider import ScoutServiceProvider

    app = Application(base_path=tmp_path)
    ScoutServiceProvider(app).boot()  # register() was never called

    assert not app.container.bound(EngineManager)


# --- the collection engine ----------------------------------------------------


async def test_the_collection_engine_keeps_no_index_of_its_own(posts: list[Post]) -> None:
    engine = CollectionEngine("collection")
    assert await engine.update(posts) is None
    assert await engine.delete(posts) is None
    assert await engine.flush(Post) is None


async def test_the_collection_engine_looks_inside_values_that_are_not_words(
    memory_db: Any,
) -> None:
    class Recipe(Searchable, Model):
        table = "posts"
        timestamps = False

        def to_searchable_array(self) -> dict[str, Any]:
            return {"id": self.id, "tags": ["stew", "pepper"], "nothing": None}

    await schema()
    await Recipe.force_create({"title": "Dinner", "body": ""})

    assert len(await Recipe.search("pepper").get()) == 1
    assert len(await Recipe.search("saffron").get()) == 0


async def test_the_collection_engine_sorts_by_a_column_that_holds_words(
    posts: list[Post],
) -> None:
    await Post.query().where("id", 1).update({"title": None})
    found = await Post.search("").order_by("title").get()
    # A missing value sorts first, and dates never meet strings.
    assert [post.id for post in found] == [1, 2, 3]


# --- full text ----------------------------------------------------------------


async def test_the_database_engine_asks_the_dialect_for_full_text(
    posts: list[Post],
) -> None:
    del posts

    class Article(Post):
        table = "posts"
        searchable_columns = ("title", "body")
        search_using_full_text = ("body",)

    engine = DatabaseEngine("database")
    query = Article.query()
    query.get_connection = lambda: type("Postgres", (), {"dialect": "postgresql"})()  # type: ignore[method-assign]

    engine._match(Article.search("scout"), query)

    sql = str(query.to_select())
    assert "to_tsvector" in sql
    # The full-text column is matched by the index, not by a second LIKE.
    assert sql.count("LIKE") == 1


# --- flushing deferred writes ---------------------------------------------------


async def test_flushing_waits_for_the_writes_a_commit_started() -> None:
    from almasix.scout.pending import _run, flush_search

    done: list[str] = []

    async def write() -> None:
        done.append("indexed")

    _run(write())
    await flush_search()
    assert done == ["indexed"]


# --- the quiet paths ------------------------------------------------------------


async def test_removing_an_empty_batch_asks_the_engine_nothing(posts: list[Post]) -> None:
    del posts
    from almasix.scout.searchable import make_searchable, remove_from_search

    fake = Scout.fake()
    await remove_from_search([])
    await make_searchable([])
    fake.assert_nothing_synced()


async def test_a_pause_covers_deleting_and_restoring_too(memory_db: Any) -> None:
    del memory_db
    await schema()
    note = await Note.force_create({"body": "kept quiet"})

    fake = Scout.fake()
    with Note.without_syncing_to_search():
        await note.delete()
        await note.restore()
    fake.assert_nothing_synced()


async def test_meilisearch_speaks_to_an_open_service_without_a_key(
    fresh_manager: EngineManager,
    faked_http: None,
) -> None:
    del fresh_manager
    from almasix.client.facade import Http

    Http.fake({"*": Http.response({"taskUid": 1})})
    await MeilisearchEngine("meilisearch", {"host": "http://open.test:7700"}).flush(Post)

    Http.assert_sent(lambda request: "Authorization" not in request.headers)


async def test_the_fake_names_the_keys_it_did_not_see_removed(posts: list[Post]) -> None:
    fake = Scout.fake()
    await posts[0].unsearchable()

    fake.assert_removed(Post, [posts[0].id])
    with pytest.raises(AssertionError, match="Nothing was removed"):
        fake.assert_removed(Post, [99])
