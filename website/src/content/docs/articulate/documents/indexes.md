---
title: Documents — Indexes
description: Declare collection indexes on the model and sync them with Smith or sync_indexes().
---

A collection needs no migration; it appears on first write. Indexes are still
worth declaring so queries stay fast and unique constraints are enforced.

## Declaring indexes

Indexes live on the model as a tuple of dicts. The shape mirrors what Mongo's
`create_index` accepts:

```python title="app/models/article.py"
class Article(Document):
    indexes = (
        {"keys": [("slug", 1)], "unique": True},
        {
            "keys": [("author_id", 1), ("created_at", -1)],
            "name": "author_recent",
        },
        {"keys": [("tags", 1)], "name": "tags_asc"},
    )
```

| Key | Meaning |
| --- | --- |
| `keys` | Sequence of `(field, direction)` pairs — `1` ascending, `-1` descending |
| `unique` | Reject duplicate values for that key |
| `name` | Explicit index name (Mongo otherwise invents one) |
| other options | Passed through to the store (TTL, partial filters, …) when the driver supports them |

The memory store enforces `unique` in process so tests catch collisions without
Mongo. Other options are best-effort there.

## Syncing

```bash title="terminal"
smith documents:index
smith documents:index --model Article
smith documents:index --pretend
smith documents:show --database mongodb
```

From code:

```python title="app/http/controllers/example_controller.py"
await Article.sync_indexes()
```

`documents:show` lists collections, document counts, and indexes for a named
document connection. If more than one document connection exists, pass
`--database`.

## What indexes are not

Almasix does not ship a Schema Blueprint for collections. Declaring indexes on
the model (and syncing them) is the supported path — the same honesty rule as
skipping SQL migrations for documents. Text indexes, TTL indexes, and Atlas
Search / vector index definitions can be passed as options where Mongo accepts
them; first-class helpers for those index kinds are not shipped yet.
