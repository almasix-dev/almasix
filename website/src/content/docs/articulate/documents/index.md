---
title: Documents (NoSQL)
description: Articulate over MongoDB and in-memory document stores — the same models, without tables or joins.
---

Articulate models normally sit on a **table**. A `Document` model sits on a
**collection** instead: MongoDB in production, an in-process store in tests.
Casts, accessors, scopes, soft deletes, events, observers, serialization, and
factories work the same way they do over SQL. What changes is that there is no
migration, no schema builder, and no joins.

```python title="app/models/article.py"
from almasix.orm import Document, HasFactory, SoftDeletes, relation


class Article(HasFactory, SoftDeletes, Document):
    connection = "mongodb"
    collection = "articles"

    fillable = ("title", "body", "tags", "author_id")
    casts = {"published": "bool"}

    indexes = ({"keys": [("title", 1)], "unique": True},)
```

```python title="app/http/controllers/example_controller.py"
article = await Article.create(title="Notes", tags=["math"])
await Article.query().where_all("tags", ["math"]).order_by_desc("created_at").get()
```

One ORM, two store kinds: SQL tables and document collections share the same
Active Record habits. Configure stores under
[Database → Document stores](/database/documents/); see the
[document store feature map](/articulate/documents/compared/) for what ships,
what is partial, and what is deliberately missing.

## In this section

| Page | What it covers |
| --- | --- |
| [Getting started](/articulate/documents/getting-started/) | Install, configure Mongo or memory, first `Document`, keys, generators |
| [Querying](/articulate/documents/querying/) | `DocumentBuilder`, document-native filters, pagination, refusals |
| [Relationships & embeds](/articulate/documents/relationships/) | References across stores, `embeds_one` / `embeds_many` |
| [Indexes](/articulate/documents/indexes/) | Declared indexes, `documents:index` / `documents:show` |
| [Aggregations](/articulate/documents/aggregations/) | Builder aggregates and `raw_aggregate` pipelines |
| [Document store feature map](/articulate/documents/compared/) | Shipped, partial, and missing features — honest gaps included |

Also see the Database section:
[Document stores (NoSQL)](/database/documents/) (config and `store()` vs
`connection()`) and [Engine support](/database/engines/).

## When to use a document store

Reach for documents when the data is naturally nested, the schema changes
often, or you want Mongo's write and query shape. Keep using SQL models when
you need joins, foreign keys, transactional DDL, or the rest of the SQL
Articulate ladder. Mixing both in one app is normal: a document can
`belongs_to` a SQL user, and a SQL model can reference a document key.

## Try it in your app

Add a `memory` (or `mongodb`) connection in `config/database.py`, define a
`Document` subclass, and create a few rows from a Smith command or a test.
Point `DOCUMENTS_CONNECTION` at `mongodb` and set `MONGODB_DSN` when you want
a real server — the same model code works on both stores.
