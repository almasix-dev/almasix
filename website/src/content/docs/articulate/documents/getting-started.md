---
title: Documents — Getting Started
description: Install Motor, configure MongoDB or the memory store, and define your first Document model.
---

## Installation

SQLite-style document work needs nothing extra. MongoDB needs Motor:

```bash title="terminal"
pip install "almasix[mongodb]"
```

Run a MongoDB server locally (Community Server or Docker) or use
[MongoDB Atlas](https://www.mongodb.com/atlas). Set the connection string in
`.env`:

```ini title=".env"
MONGODB_DSN="mongodb://localhost:27017"
MONGODB_DATABASE="almasix"
# Atlas example:
# MONGODB_DSN="mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority"
```

## Configuration

Document connections live in `config/database.py` beside the SQL ones. The
database-side story — full config, env vars, `store()` vs `connection()`, and
when to choose collections — is under
[Database → Document stores](/database/documents/). A short reminder for model
authors:

```python title="config/database.py"
"mongodb": {
    "driver": "mongodb",
    "dsn": env("MONGODB_DSN", ""),
    "database": env("MONGODB_DATABASE", "almasix"),
},
"documents": {"driver": "memory"},
```

Point a model at a connection with `connection = "mongodb"` (or whatever name
you gave the block). A new app's scaffold already includes both blocks.

## Store vs connection

```python title="app/http/controllers/example_controller.py"
from almasix.orm import get_manager

manager = get_manager()
manager.store("mongodb")          # DocumentStore
manager.connection("sqlite")      # SQL Connection
manager.is_document("mongodb")    # True
# manager.connection("mongodb")   # ConnectionError_ — use store()
```

More detail: [Document stores](/database/documents/).

## Your first Document

```python title="app/models/article.py"
from almasix.orm import Document, HasFactory, SoftDeletes


class Article(HasFactory, SoftDeletes, Document):
    connection = "mongodb"
    collection = "articles"   # optional; defaults to the plural snake class name

    fillable = ("title", "body", "tags", "author_id", "published")
    casts = {"published": "bool", "tags": "array"}

    indexes = (
        {"keys": [("slug", 1)], "unique": True},
    )
```

`Document` is an Articulate `Model`. Everything you already know —
`fillable` / `guarded`, casts, accessors, scopes, soft deletes, factories,
events, serialization — applies. Collections appear on first write; there is
no migration.

```python title="app/http/controllers/example_controller.py"
article = await Article.create(title="Notes", tags=["math"], published=True)
found = await Article.find(article.get_key())
await Article.query().where("published", True).count()
```

## Keys

A document's primary key is `_id`:

| Setting | Default on `Document` |
| --- | --- |
| `primary_key` | `"_id"` |
| `incrementing` | `False` |
| `key_type` | `"string"` |

The store generates the key on insert unless you set `_id` yourself before
saving. The memory store always uses a 24-character hex string (ObjectId-shaped).
MongoDB returns whatever Motor inserted — often a BSON `ObjectId` instance —
rather than a framework wrapper type. Treat keys as opaque values you get from
`get_key()` / `find`, or set your own string/`HasUuids` / `HasUlids` keys when
you want a stable application-level identifier.

`find`, `where_key`, route model binding, and the UUID/ULID mixins work the
same as on SQL models.

## Generating models

```bash title="terminal"
smith make:document Article
smith make:document Article --factory
smith make:document Address --embed
```

Those write `app/models/article.py`, optionally
`database/factories/article_factory.py`, or an `EmbeddedDocument` subclass.

## Factories and soft deletes

Nothing is special-cased. `HasFactory` writes documents; `SoftDeletes` filters
on `deleted_at` the same way it filters a table:

```python title="app/http/controllers/example_controller.py"
await Article.factory().count(3).create()
await article.delete()                 # soft
await Article.with_trashed().count()
await article.restore()
await article.force_delete()
```

Seeders that call document factories work once the model's connection points
at a document store.
