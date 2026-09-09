"""The MongoDB store — the query shape, translated into Mongo's own.

Motor lives behind this file and appears in no application signature. The
translation is the interesting part, and it is what the tests check: what
filter, sort, and pipeline a given Articulate query becomes.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import quote_plus

from almasix.orm.documents.filters import Condition, Query
from almasix.orm.documents.stores.base import DocumentStore

#: Articulate's operators, as Mongo spells them.
_COMPARISON = {"!=": "$ne", "<": "$lt", "<=": "$lte", ">": "$gt", ">=": "$gte"}


class MongoNotInstalled(RuntimeError):
    """The `mongodb` extra is not installed."""

    def __init__(self) -> None:
        super().__init__(
            "The MongoDB store needs Motor: pip install 'almasix[mongodb]' "
            "(or `pip install motor`)."
        )


def build_dsn(config: Mapping[str, Any]) -> str:
    """A Mongo URI from a Laravel-shaped connection dict."""
    dsn = config.get("dsn") or config.get("url")
    if dsn:
        return str(dsn)
    host = config.get("host", "127.0.0.1")
    port = config.get("port", 27017)
    username = config.get("username")
    password = config.get("password")
    credentials = ""
    if username:
        credentials = quote_plus(str(username))
        if password:
            credentials = f"{credentials}:{quote_plus(str(password))}"
        credentials = f"{credentials}@"
    return f"mongodb://{credentials}{host}:{port}"


def to_filter(conditions: Sequence[Condition]) -> dict[str, Any]:
    """Turn a where list into one Mongo filter document.

    `and` conditions merge; the moment an `or` appears the whole list becomes
    an `$or` of the groups either side of it, which is what SQL means by
    precedence here.
    """
    if not conditions:
        return {}

    groups: list[list[Condition]] = [[]]
    for condition in conditions:
        if condition.boolean == "or" and groups[-1]:
            groups.append([])
        groups[-1].append(condition)

    compiled = [_conjunction(group) for group in groups]
    if len(compiled) == 1:
        return compiled[0]
    return {"$or": compiled}


def _conjunction(conditions: Sequence[Condition]) -> dict[str, Any]:
    clauses = [_one(condition) for condition in conditions]
    clauses = [clause for clause in clauses if clause]
    if not clauses:
        return {}
    if len(clauses) == 1:
        return clauses[0]
    # Separate keys merge cleanly; repeated ones need $and to survive.
    merged: dict[str, Any] = {}
    for clause in clauses:
        if any(key in merged for key in clause):
            return {"$and": clauses}
        merged.update(clause)
    return merged


def _one(condition: Condition) -> dict[str, Any]:
    operator = condition.operator
    column = condition.column
    value = condition.value

    if operator == "group":
        return to_filter(value)
    if operator == "raw":
        return dict(value)
    if operator == "=":
        return {column: value}
    if operator in _COMPARISON:
        return {column: {_COMPARISON[operator]: value}}
    if operator == "in":
        return {column: {"$in": list(value)}}
    if operator == "not in":
        return {column: {"$nin": list(value)}}
    if operator == "null":
        return {column: None}
    if operator == "not null":
        return {column: {"$ne": None}}
    if operator == "between":
        return {column: {"$gte": value[0], "$lte": value[1]}}
    if operator == "not between":
        return {"$or": [{column: {"$lt": value[0]}}, {column: {"$gt": value[1]}}]}
    if operator == "like":
        pattern = re.escape(str(value)).replace("%", ".*").replace("_", ".")
        return {column: {"$regex": f"^{pattern}$", "$options": "i"}}
    if operator == "regex":
        return {column: {"$regex": str(value)}}
    if operator == "exists":
        return {column: {"$exists": bool(value)}}
    if operator == "all":
        return {column: {"$all": list(value)}}
    return {column: {"$size": int(value)}}  # "size"


def to_sort(query: Query) -> list[tuple[str, int]]:
    return [(order.column, -1 if order.descending else 1) for order in query.orders]


class MongoStore(DocumentStore):
    """Documents in MongoDB, reached through Motor."""

    driver = "mongodb"

    def __init__(
        self,
        name: str,
        config: Mapping[str, Any] | None = None,
        client: Any = None,
    ) -> None:
        super().__init__(name, config)
        self.database_name = str(self.config.get("database") or "almasix")
        self.key_name = str(self.config.get("key", "_id"))
        self._client = client

    # --- plumbing -----------------------------------------------------------

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = self._connect()
        return self._client

    def _connect(self) -> Any:
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
        except ImportError as exc:  # pragma: no cover - depends on the environment
            raise MongoNotInstalled from exc
        options = dict(self.config.get("options") or {})
        return AsyncIOMotorClient(build_dsn(self.config), **options)

    def collection(self, name: str) -> Any:
        return self.client[self.database_name][name]

    # --- reads --------------------------------------------------------------

    async def find(self, query: Query) -> list[dict[str, Any]]:
        projection = {field: 1 for field in query.projection} or None
        if query.distinct:
            values = await self.collection(query.collection).distinct(
                query.distinct, to_filter(query.wheres)
            )
            return [{query.distinct: value} for value in values]

        cursor = self.collection(query.collection).find(to_filter(query.wheres), projection)
        if query.orders:
            cursor = cursor.sort(to_sort(query))
        if query.offset:
            cursor = cursor.skip(query.offset)
        if query.limit is not None:
            cursor = cursor.limit(query.limit)
        return [dict(row) async for row in cursor]

    async def count(self, query: Query) -> int:
        options: dict[str, Any] = {}
        if query.offset:
            options["skip"] = query.offset
        if query.limit is not None:
            options["limit"] = query.limit
        return int(
            await self.collection(query.collection).count_documents(
                to_filter(query.wheres), **options
            )
        )

    async def aggregate(self, query: Query, function: str, column: str | None = None) -> Any:
        if function == "count":
            return await self.count(query)
        pipeline: list[dict[str, Any]] = [
            {"$match": to_filter(query.wheres)},
            {"$group": {"_id": None, "value": {f"${function}": f"${column}"}}},
        ]
        rows = [row async for row in self.collection(query.collection).aggregate(pipeline)]
        return rows[0]["value"] if rows else None

    async def group_count(self, query: Query, column: str) -> dict[Any, int]:
        pipeline: list[dict[str, Any]] = [
            {"$match": to_filter(query.wheres)},
            {"$group": {"_id": f"${column}", "value": {"$sum": 1}}},
        ]
        rows = [row async for row in self.collection(query.collection).aggregate(pipeline)]
        return {row["_id"]: int(row["value"]) for row in rows}

    async def raw_aggregate(
        self, collection: str, pipeline: Sequence[Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        """Run a pipeline Almasix did not write — the escape hatch."""
        cursor = self.collection(collection).aggregate([dict(stage) for stage in pipeline])
        return [dict(row) async for row in cursor]

    # --- writes -------------------------------------------------------------

    async def insert(self, collection: str, documents: Sequence[Mapping[str, Any]]) -> list[Any]:
        rows = [
            {
                key: value
                for key, value in dict(row).items()
                if value is not None or key != self.key_name
            }
            for row in documents
        ]
        if not rows:
            return []
        if len(rows) == 1:
            result = await self.collection(collection).insert_one(rows[0])
            return [result.inserted_id]
        result = await self.collection(collection).insert_many(rows)
        return list(result.inserted_ids)

    async def update(self, query: Query, values: Mapping[str, Any]) -> int:
        if not values:
            return 0
        result = await self.collection(query.collection).update_many(
            to_filter(query.wheres), {"$set": dict(values)}
        )
        return int(result.modified_count)

    async def increment(
        self,
        query: Query,
        amounts: Mapping[str, Any],
        values: Mapping[str, Any],
    ) -> int:
        update: dict[str, Any] = {"$inc": dict(amounts)}
        if values:
            update["$set"] = dict(values)
        result = await self.collection(query.collection).update_many(
            to_filter(query.wheres), update
        )
        return int(result.modified_count)

    async def delete(self, query: Query) -> int:
        result = await self.collection(query.collection).delete_many(to_filter(query.wheres))
        return int(result.deleted_count)

    # --- collections and indexes -------------------------------------------

    async def create_index(
        self,
        collection: str,
        keys: Sequence[tuple[str, int]],
        *,
        unique: bool = False,
        name: str | None = None,
    ) -> str:
        options: dict[str, Any] = {"unique": unique}
        if name:
            options["name"] = name
        return str(
            await self.collection(collection).create_index(
                [(field, int(direction)) for field, direction in keys], **options
            )
        )

    async def indexes(self, collection: str) -> list[dict[str, Any]]:
        found = await self.collection(collection).index_information()
        return [
            {
                "name": name,
                "keys": [(field, int(direction)) for field, direction in spec.get("key", [])],
                "unique": bool(spec.get("unique", False)),
            }
            for name, spec in found.items()
        ]

    async def drop_collection(self, collection: str) -> None:
        await self.client[self.database_name].drop_collection(collection)

    async def collections(self) -> list[str]:
        return sorted(await self.client[self.database_name].list_collection_names())

    async def disconnect(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
