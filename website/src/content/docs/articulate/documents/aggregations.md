---
title: Documents — Aggregations
description: Use builder aggregates for simple totals, and raw_aggregate for Mongo pipelines.
---

## Builder aggregates

For single-field totals the builder is enough:

```python
await Article.query().where("published", True).count()
await Article.query().sum("views")
await Article.query().avg("views")
await Article.query().min("views")
await Article.query().max("views")
```

These run on both Mongo and the memory store. They are not a substitute for
`GROUP BY` — see below.

## Raw pipelines

When you need grouping, `$lookup`, `$facet`, or anything the builder refuses,
hand Mongo a pipeline:

```python
rows = await Article.query().raw_aggregate([
    {"$match": {"published": True}},
    {"$group": {"_id": "$author_id", "views": {"$sum": "$views"}}},
    {"$sort": {"views": -1}},
])
```

`raw_aggregate` is Mongo-only. The memory store raises rather than pretending
to implement the aggregation language. In tests that need pipeline results,
point the model at Mongo or assert the builder path instead.

### Common pipeline shapes

| Goal | Approach |
| --- | --- |
| Group and total | `$match` → `$group` → `$sort` |
| Join another collection | `$lookup` (then `$unwind` if you need rows) |
| Union collections | `$unionWith` |
| Computed fields | `$addFields` / `$project` |
| Text search | `$match` with `$text`, or Atlas Search stages via `where_raw` / pipeline |

There is no typed Aggregation Builder yet — pipelines are lists of mappings.
That keeps the escape hatch honest: what you write is what Motor runs.

## When the builder refuses

```python
Article.query().group_by("author_id")   # UnsupportedQueryError → raw_aggregate()
Article.query().having("views", ">", 1)
Article.query().join("authors", ...)
```

Use the error message as the redirect: every SQL-only call names
`raw_aggregate()` (or a document-native filter) instead of inventing a wrong
result.
