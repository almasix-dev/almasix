"""Searching the table you already have.

The database engine puts the phrase into the query instead of into a service:
`LIKE` by default, a prefix match where you asked for one, and the database's
own full-text index where the dialect has one. There is nothing to import and
nothing to keep in sync, which for most applications is the whole answer.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from almasix.orm.collection import Collection
from almasix.scout.builder import SOFT_DELETED
from almasix.scout.engines.base import Engine

#: Dialects whose full-text syntax we speak. Everywhere else a column marked
#: for full text is searched with `LIKE`, which is slower but never wrong.
FULL_TEXT_DIALECTS = ("postgresql", "mysql", "mariadb")


class DatabaseEngine(Engine):
    """Searches the model's own table in SQL."""

    driver = "database"

    async def update(self, models: Sequence[Any]) -> None:
        """Nothing to do: the table is the index."""
        return

    async def delete(self, models: Sequence[Any]) -> None:
        return None

    async def flush(self, model: Any) -> None:
        return None

    async def search(self, builder: Any) -> Any:
        query = await self._query(builder)
        total = await query.clone().count()
        if builder.limit:
            query = query.limit(builder.limit)
        return {"models": list(await query.get()), "total": total}

    async def paginate(self, builder: Any, per_page: int, page: int) -> Any:
        query = await self._query(builder)
        total = await query.clone().count()
        models = await query.for_page(int(page), int(per_page)).get()
        return {"models": list(models), "total": total}

    def map_ids(self, results: Any) -> list[Any]:
        return [model.get_scout_key() for model in results["models"]]

    def total_count(self, results: Any) -> int:
        return int(results["total"])

    async def map(self, builder: Any, results: Any, model: Any) -> Collection[Any]:
        """The rows are already models — Laravel's engine does the same.

        This is why `query_using()` filters here and only shapes elsewhere:
        its constraints are part of the search query itself.
        """
        del builder, model
        return Collection(list(results["models"]))

    # --- building the query -------------------------------------------------

    async def _query(self, builder: Any) -> Any:
        model = builder.model
        query = model.scout_base_query()

        if builder.query_callback is not None:
            query = builder.query_callback(query) or query

        for field, value in builder.wheres.items():
            if field != SOFT_DELETED:
                query = query.where(field, "=", value)
        for field, values in builder.where_ins.items():
            query = query.where_in(field, values)
        for field, values in builder.where_not_ins.items():
            query = query.where_not_in(field, values)

        query = self._trashed(builder, query)

        if builder.query:
            self._match(builder, query)

        for order in builder.orders:
            query = query.order_by(order["column"], order["direction"])
        if not builder.orders:
            query = query.order_by(model.primary_key, "desc")
        return query

    def _trashed(self, builder: Any, query: Any) -> Any:
        """`with_trashed()` and `only_trashed()`, in SQL rather than a flag."""
        model = builder.model
        wanted = builder.wheres.get(SOFT_DELETED)
        if wanted is None or not getattr(model, "_soft_deletes", False):
            return query
        column = f"{model.get_table()}.{model.deleted_at}"
        return query.where_not_null(column) if int(wanted) == 1 else query.where_null(column)

    def _match(self, builder: Any, query: Any) -> None:
        """Add the phrase itself: one OR group over the searchable columns."""
        model = builder.model
        columns = _columns(model)
        if not columns:
            raise ValueError(
                f"{model.__name__} has no searchable columns. Return them from "
                "to_searchable_array(), or name them in `searchable_columns`."
            )

        prefix = set(getattr(model, "search_using_prefix", ()) or ())
        full_text = [c for c in getattr(model, "search_using_full_text", ()) or () if c in columns]
        dialect = query.get_connection().dialect
        phrase = builder.query

        def group(nested: Any) -> None:
            boolean = "and"
            for column in columns:
                if column in full_text and dialect in FULL_TEXT_DIALECTS:
                    continue
                pattern = f"{phrase}%" if column in prefix else f"%{phrase}%"
                nested.where(f"{model.get_table()}.{column}", "like", pattern, boolean)
                boolean = "or"
            if full_text and dialect in FULL_TEXT_DIALECTS:
                sql = full_text_clause(dialect, model.get_table(), full_text)
                nested.where_raw(sql, boolean, {"scout_phrase": phrase})

        query.where(group)


def _columns(model: Any) -> list[str]:
    """Which columns the phrase is looked for in."""
    declared = getattr(model, "searchable_columns", ()) or ()
    if declared:
        return [str(column) for column in declared]
    try:
        # Laravel reads the keys off an empty model too. A searchable array
        # built from attributes the row has not loaded cannot answer, which
        # is what `searchable_columns` is for.
        payload = model().to_searchable_array()
    except Exception:  # noqa: BLE001 — an unanswerable array is a missing declaration
        payload = {}
    return [key for key in payload if key != SOFT_DELETED]


def full_text_clause(dialect: str, table: str, columns: Sequence[str]) -> str:
    """The dialect's own full-text predicate, bound to `:scout_phrase`."""
    qualified = [f"{table}.{column}" for column in columns]
    if dialect == "postgresql":
        document = " || ' ' || ".join(f"coalesce({column}, '')" for column in qualified)
        return f"to_tsvector('english', {document}) @@ plainto_tsquery('english', :scout_phrase)"
    return f"MATCH ({', '.join(qualified)}) AGAINST (:scout_phrase IN NATURAL LANGUAGE MODE)"
