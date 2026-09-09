---
title: Documents (NoSQL)
description: Articulate over MongoDB and in-memory document stores — the same models, without tables or joins.
---

Articulate models normally sit on a **table**. A `Document` model sits on a
**collection** instead: MongoDB in production, an in-process store in tests.
Casts, accessors, scopes, soft deletes, events, observers, serialization, and
factories work the same way they do over SQL. What changes is that there is no
migration, no schema builder, and no joins.

```python
# app/models/article.py
from almasix.orm import Document, HasFactory, SoftDeletes, relation


class Article(HasFactory, SoftDeletes, Document):
    connection = "mongodb"
    collection = "articles"

    fillable = ("title", "body", "tags", "author_id")
    casts = {"published": "bool"}

    indexes = ({"keys": [("title", 1)], "unique": True},)
```

```python
article = await Article.create(title="Notes", tags=["math"])
await Article.query().where_all("tags", ["math"]).order_by_desc("created_at").get()
```

Laravel 13 documents MongoDB through the official
[`mongodb/laravel-mongodb`](https://laravel.com/docs/13.x/mongodb) package.
Almasix chases that Eloquent-on-collections surface inside Articulate — one ORM,
two store kinds — and names where it deliberately stops. Configure stores under
[Database → Document stores](/database/documents/); see
[Compared with Laravel](/articulate/documents/compared/) for the full map.

## In this section

| Page | What it covers |
| --- | --- |
| [Getting started](/articulate/documents/getting-started/) | Install, configure Mongo or memory, first `Document`, keys, generators |
| [Querying](/articulate/documents/querying/) | `DocumentBuilder`, document-native filters, pagination, refusals |
| [Relationships & embeds](/articulate/documents/relationships/) | References across stores, `embeds_one` / `embeds_many` |
| [Indexes](/articulate/documents/indexes/) | Declared indexes, `documents:index` / `documents:show` |
| [Aggregations](/articulate/documents/aggregations/) | Builder aggregates and `raw_aggregate` pipelines |
| [Compared with Laravel](/articulate/documents/compared/) | Honest parity vs Laravel 13 MongoDB features |

Also see the Database section:
[Document stores (NoSQL)](/database/documents/) (config and `store()` vs
`connection()`) and [Engine support](/database/engines/).

## When to use a document store

Reach for documents when the data is naturally nested, the schema changes
often, or you want Mongo's write and query shape. Keep using SQL models when
you need joins, foreign keys, transactional DDL, or the rest of the SQL
Articulate ladder. Mixing both in one app is normal: a document can
`belongs_to` a SQL user, and a SQL model can reference a document key.

## Living example

The progress app keeps an `Activity` document on the in-process `memory` store
(point `DOCUMENTS_CONNECTION` at `mongodb` to use a real server):

```bash
cd examples/progress
python smith progress:documents
# GET /api/documents
```
