---
title: Documents — Querying
description: Filter, sort, paginate, and update collections with DocumentBuilder — plus the operators SQL never needed.
---

`Document.query()` returns a `DocumentBuilder`. It spells the SQL builder's
surface for operations a collection can answer, and raises
`UnsupportedQueryError` for the rest.

## Reading

```python title="app/http/controllers/example_controller.py"
await Article.query().where("views", ">", 100).count()
await Article.query().where_in("status", ["draft", "review"]).get()
await Article.query().where_null("deleted_at").order_by("created_at").limit(10).get()
await Article.query().where("author.city", "Nairobi").get()   # dotted paths
await Article.query().order_by_desc("created_at").first()
await Article.find(key)
await Article.query().pluck("title")
await Article.query().exists()
```

Chaining works as on SQL: `when` / `unless` / `tap`, local scopes,
`select` / `distinct`, `offset` / `limit`, and eager loading via `with_` /
`with_count`.

### Comparison operators

The usual operators (`=`, `!=`, `<`, `<=`, `>`, `>=`, `like`, `in`, `not in`,
`null` / `not null`) translate to Mongo filters. Groups use nested
`where(lambda q: …)` the same way the SQL builder does; `or_where` starts a
new `$or` branch.

### Document-native filters

Four filters exist because documents do, and SQL has no use for them:

| Method | Matches |
| --- | --- |
| `where_regex("title", "^No")` | a field against a regular expression |
| `where_exists_field("subtitle")` | documents that carry the field at all — missing is not null |
| `where_all("tags", ["a", "b"])` | an array field containing every value |
| `where_size("tags", 3)` | an array field of exactly that length |

```python title="app/http/controllers/example_controller.py"
await Article.query().where_all("tags", ["math"]).where_size("tags", 2).get()
await Article.query().where_regex("title", r"^Note", flags="i").get()
await Article.query().where_exists_field("subtitle").get()
```

### Raw filters

`where_raw()` takes a filter Almasix did not write. Hand it a mapping and it
goes to the engine untouched; hand it a callable and the memory store evaluates
it in Python (so tests stay offline):

```python title="app/http/controllers/example_controller.py"
await Article.query().where_raw({"$text": {"$search": "engines"}}).get()
await Article.query().where_raw(lambda row: row["views"] > 100).get()
```

Text search, geospatial operators, and Atlas Search expressions belong here
until Almasix grows first-class helpers for them.

## Writing

```python title="app/http/controllers/example_controller.py"
await Article.query().insert({"title": "One", "views": 0})
await Article.query().where("views", 0).update({"published": False})
await Article.query().where("id", key).upsert(
    {"title": "One", "views": 1},
    unique_by=["_id"],
    update=["views"],
)
await Article.query().where("views", ">", 0).increment("views", 1)
await Article.query().where("draft", True).delete()
await Article.query().truncate()
```

`insert_get_id`, `update_or_insert`, `increment` / `decrement`, and model
`create` / `save` / `delete` follow the Articulate conventions you already use
on SQL models.

## Pagination and chunking

Offset pagination and simple pagination work on collections:

```python title="app/http/controllers/example_controller.py"
page = await Article.query().order_by("created_at").paginate(15, page=2)
simple = await Article.query().order_by("created_at").simple_paginate(15)
await Article.query().chunk(100, handle)
async for article in Article.query().lazy(100):
    ...
```

Cursor / keyset pagination on document builders is not shipped yet — use
offset pagination or a raw ordered query with a range on `_id` / a sort field.

## What a store will not do

A document store has no joins, no `GROUP BY`, and no SQL expressions. Rather
than quietly returning something else, those calls raise
`UnsupportedQueryError` and name the alternative:

```python title="app/http/controllers/example_controller.py"
Article.query().join("authors", ...)    # UnsupportedQueryError
Article.query().group_by("author_id")   # → use raw_aggregate()
Article.query().having("views", ">", 1) # → use raw_aggregate()
Article.query().where_column("a", "b")  # → use raw_aggregate() and $expr
Article.query().union(other)            # → use raw_aggregate() and $unionWith
```

See [Aggregations](/articulate/documents/aggregations/) for pipelines.
