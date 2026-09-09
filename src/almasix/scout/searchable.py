"""The `Searchable` mixin — what makes a model findable.

Mix it in and the model keeps its index in step with the database on its own:
a save indexes the row, a delete removes it, and `Model.search("...")` reads
it back. Everything the mixin does can be overridden per model — the index
name, the key, the data, the engine, and whether a row belongs in an index at
all.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, ClassVar

from almasix.scout.builder import SOFT_DELETED, SearchBuilder
from almasix.scout.helpers import get_engine_manager

#: Model classes whose writes are not reaching the index right now.
_PAUSED: ContextVar[frozenset[type]] = ContextVar("almasix_scout_paused", default=frozenset())


class Searchable:
    """Mixin: the model is indexed, and searchable.

    Mix in **before** `Model` so the metaclass boots it::

        class Post(Searchable, Model):
            def to_searchable_array(self) -> dict[str, Any]:
                return {"id": self.id, "title": self.title}
    """

    #: Columns the `database` engine searches; the searchable array's keys
    #: when this is empty.
    searchable_columns: ClassVar[tuple[str, ...]] = ()
    #: Columns matched from the start of the string (`example%`).
    search_using_prefix: ClassVar[tuple[str, ...]] = ()
    #: Columns handed to the database's own full-text index.
    search_using_full_text: ClassVar[tuple[str, ...]] = ()

    @staticmethod
    def boot_searchable(cls: Any) -> None:
        cls.listen("saved", _on_saved)
        cls.listen("deleted", _on_deleted)
        cls.listen("restored", _on_restored)

    # --- what the index holds ----------------------------------------------

    def to_searchable_array(self) -> dict[str, Any]:
        """The data that goes into the index — the whole model by default."""
        return dict(self.to_dict())  # type: ignore[attr-defined]

    def scout_metadata(self) -> dict[str, Any]:
        """What Scout adds to the record on the model's behalf."""
        if type(self).uses_soft_delete_metadata():
            return {SOFT_DELETED: int(bool(self.trashed()))}  # type: ignore[attr-defined]
        return {}

    def should_be_searchable(self) -> bool:
        """Whether this record belongs in the index at all."""
        return True

    def search_index_should_be_updated(self) -> bool:
        """Whether this write is worth re-indexing for."""
        return True

    @classmethod
    def searchable_as(cls) -> str:
        """The index this model lives in — its table, behind `scout.prefix`.

        A classmethod, where Laravel's is an instance method: `scout:index`
        and friends ask a class, and there is nothing per-row about it.
        """
        return f"{get_engine_manager().prefix}{cls.get_table()}"  # type: ignore[attr-defined]

    @classmethod
    def get_scout_key_name(cls) -> str:
        """The attribute the index is keyed by."""
        return str(cls.primary_key)  # type: ignore[attr-defined]

    def get_scout_key(self) -> Any:
        """The value the index is keyed by."""
        return self.get_key()  # type: ignore[attr-defined]

    @classmethod
    def searchable_using(cls) -> Any:
        """The engine this model is indexed and searched with."""
        return get_engine_manager().engine()

    @classmethod
    def uses_soft_delete_metadata(cls) -> bool:
        """Whether trashed rows stay in the index behind a flag."""
        return bool(getattr(cls, "_soft_deletes", False)) and get_engine_manager().soft_delete

    # --- searching ----------------------------------------------------------

    @classmethod
    def search(cls, query: str = "", callback: Callable[..., Any] | None = None) -> SearchBuilder:
        """Start a search: `await Post.search("laravel").get()`."""
        return SearchBuilder(cls, query, callback, soft_delete=cls.uses_soft_delete_metadata())

    @classmethod
    def scout_base_query(cls) -> Any:
        """The query search reads rows through — trashed rows included when
        they are indexed, so a soft deleted hit can still be shown."""
        if cls.uses_soft_delete_metadata():
            return cls.with_trashed()  # type: ignore[attr-defined]
        return cls.query()  # type: ignore[attr-defined]

    @classmethod
    def query_scout_models_by_ids(cls, builder: SearchBuilder, keys: Sequence[Any]) -> Any:
        """The query that turns matched keys back into models."""
        del builder
        return cls.scout_base_query().where_in(cls.get_scout_key_name(), list(keys))

    # --- keeping the index in step -----------------------------------------

    async def searchable(self) -> None:
        """Put this model into its index, now or through the queue."""
        await make_searchable([self])

    async def unsearchable(self) -> None:
        """Take this model out of its index."""
        await remove_from_search([self])

    @classmethod
    async def make_all_searchable(cls, chunk: int | None = None) -> int:
        """Import every row that belongs in the index (`scout:import`)."""
        size = int(chunk or get_engine_manager().chunk_size("searchable"))
        query = cls.make_all_searchable_using(cls.scout_base_query())
        imported = 0

        async def index(models: Any) -> None:
            nonlocal imported
            wanted = [model for model in models if model.should_be_searchable()]
            await make_searchable(wanted)
            imported += len(wanted)

        await query.order_by(cls.get_scout_key_name()).chunk(size, index)
        return imported

    @classmethod
    async def remove_all_from_search(cls) -> None:
        """Empty this model's index (`scout:flush`)."""
        await cls.searchable_using().flush(cls)

    @classmethod
    def make_all_searchable_using(cls, query: Any) -> Any:
        """Hook: shape the query a full import reads through (eager loads)."""
        return query

    @classmethod
    def make_searchable_using(cls, models: Sequence[Any]) -> Sequence[Any]:
        """Hook: shape a batch of models on its way to the index."""
        return models

    # --- pausing ------------------------------------------------------------

    @classmethod
    @contextmanager
    def without_syncing_to_search(cls) -> Iterator[None]:
        """Write without touching the index::

        with Post.without_syncing_to_search():
            await post.save()
        """
        token = _PAUSED.set(_PAUSED.get() | {cls})
        try:
            yield
        finally:
            _PAUSED.reset(token)

    @classmethod
    def disable_search_syncing(cls) -> None:
        """Stop syncing this model until something enables it again."""
        _PAUSED.set(_PAUSED.get() | {cls})

    @classmethod
    def enable_search_syncing(cls) -> None:
        _PAUSED.set(_PAUSED.get() - {cls})

    @classmethod
    def search_syncing_paused(cls) -> bool:
        return any(issubclass(cls, paused) for paused in _PAUSED.get())


# --- the writes themselves --------------------------------------------------


async def make_searchable(models: Sequence[Any]) -> None:
    """Index a batch of models — through the queue when search is queued."""
    records = list(models)
    if not records:
        return
    records = list(type(records[0]).make_searchable_using(records))
    manager = get_engine_manager()

    if manager.queues:
        from almasix.scout.jobs import MakeSearchable

        await _dispatch(MakeSearchable.for_models(records), manager)
        return

    engine = type(records[0]).searchable_using()
    for batch in _chunks(records, manager.chunk_size("searchable")):
        await engine.update(batch)


async def remove_from_search(models: Sequence[Any]) -> None:
    """Take a batch of models out of their index."""
    records = list(models)
    if not records:
        return
    manager = get_engine_manager()

    if manager.queues:
        from almasix.scout.jobs import RemoveFromSearch

        await _dispatch(RemoveFromSearch.for_models(records), manager)
        return

    engine = type(records[0]).searchable_using()
    for batch in _chunks(records, manager.chunk_size("unsearchable")):
        await engine.delete(batch)


async def _dispatch(job: Any, manager: Any) -> None:
    """Push an indexing job, and fall back to doing it here without a queue."""
    from almasix.queue.helpers import dispatch as queue_dispatch

    options = manager.queue_options
    if options.get("connection"):
        job.connection = str(options["connection"])
    if options.get("queue"):
        job.queue = str(options["queue"])

    try:
        await queue_dispatch(job)
    except KeyError:
        # An application with no queue configured still keeps its index in
        # step; losing the write would be a poor trade for a rule nobody set.
        await job.handle()


def _chunks(records: list[Any], size: int) -> list[list[Any]]:
    return [records[start : start + size] for start in range(0, len(records), max(size, 1))]


# --- the model listeners ----------------------------------------------------


async def _on_saved(model: Any) -> None:
    if type(model).search_syncing_paused():
        return
    await _after_commit(model, lambda: _sync(model))


async def _on_deleted(model: Any) -> None:
    if type(model).search_syncing_paused():
        return
    # A soft delete leaves the row in place: when trashed rows are indexed it
    # is a re-index, and otherwise the record goes.
    if type(model).uses_soft_delete_metadata() and model.exists:
        await _after_commit(model, lambda: _sync(model))
        return
    await _after_commit(model, model.unsearchable)


async def _on_restored(model: Any) -> None:
    if type(model).search_syncing_paused():
        return
    await _after_commit(model, lambda: _sync(model))


async def _sync(model: Any) -> None:
    """Index or unindex one model, depending on what it says about itself."""
    if not model.should_be_searchable():
        await model.unsearchable()
        return
    if model.search_index_should_be_updated():
        await model.searchable()


async def _after_commit(model: Any, work: Callable[[], Any]) -> None:
    """Index now, or once the surrounding transaction commits."""
    from almasix.scout.pending import defer_until_commit

    if not get_engine_manager().after_commit:
        await work()
        return
    if not defer_until_commit(model, work):
        await work()
