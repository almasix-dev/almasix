---
title: Documents (NoSQL)
description: Articulate over MongoDB and other document stores — collections, embedded documents, and the queries a store can honestly answer.
---

Articulate models normally sit on a table. A `Document` model sits on a
*collection* instead: MongoDB in production, an in-process store in tests. The
model surface does not change — casts, accessors, scopes, soft deletes, events,
observers, serialization, and factories all work exactly as they do over SQL.
What changes is that there is no migration, no schema, and no joins.

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
await Article.query().where("tags", "all", ["math"]).order_by_desc("created_at").get()
```

Laravel has no first-party NoSQL support; the reference point for parity here
is the community `mongodb/laravel-mongodb` package, which Almasix follows in
spirit — a model that behaves like every other model — while spelling things
the way the rest of Almasix does.

## Configuring a store

Document connections live in `config/database.py` beside the SQL ones, told
apart by their driver:

```python
config = {
    "connections": {
        "mongodb": {
            "driver": "mongodb",
            "dsn": env("MONGODB_DSN", ""),
            "host": env("MONGODB_HOST", "127.0.0.1"),
            "port": env("MONGODB_PORT", 27017),
            "database": env("MONGODB_DATABASE", "almasix"),
            "username": env("MONGODB_USERNAME", ""),
            "password": env("MONGODB_PASSWORD", ""),
        },
        "memory": {"driver": "memory"},
    },
}
```

The `mongodb` driver needs Motor:

```bash
pip install "almasix[mongodb]"
```

The `memory` driver needs nothing. It keeps documents in the running process
and implements the same semantics, which makes it the document equivalent of
an in-memory SQLite database: good for tests, demos, and a laptop with no
server running.

`DB` resolves both kinds and refuses to confuse them:

```python
from almasix.orm import get_manager

get_manager().store("mongodb")        # a DocumentStore
get_manager().connection("sqlite")    # a SQL Connection
get_manager().is_document("mongodb")  # True
get_manager().connection("mongodb")   # ConnectionError_: reach it with store()
```

## Keys

A document's key is `_id`, a string, and the store generates it — so
`primary_key = "_id"`, `incrementing = False`, and `key_type = "string"` are
the defaults on `Document`. Set `_id` yourself before saving and that value is
kept. The rest of Articulate's key handling (`find`, `where_key`, route model
binding, `HasUuids`) is unchanged.

## Querying

`Document.query()` returns a `DocumentBuilder`, which spells everything the
SQL builder spells for the operations a collection can answer:

```python
await Article.query().where("views", ">", 100).count()
await Article.query().where_in("status", ["draft", "review"]).get()
await Article.query().where_null("deleted_at").order_by("created_at").limit(10).get()
await Article.query().where("author.city", "Nairobi").get()   # dotted paths
await Article.query().paginate(15, page=2)
await Article.query().sum("views")
await Article.query().chunk(100, handle)
```

Four filters exist because documents do, and SQL has no use for them:

| Method | Matches |
| --- | --- |
| `where_regex("title", "^No")` | a field against a regular expression |
| `where_exists_field("subtitle")` | documents that carry the field at all — missing is not null |
| `where_all("tags", ["a", "b"])` | an array field containing every value |
| `where_size("tags", 3)` | an array field of exactly that length |

`where_raw()` takes a filter Almasix did not write. Hand it a mapping and it
goes to the engine untouched; hand it a callable and the memory store evaluates
it in Python, which is how a test keeps working without Mongo:

```python
await Article.query().where_raw({"$text": {"$search": "engines"}}).get()
await Article.query().where_raw(lambda row: row["views"] > 100).get()
```

For anything past the builder, `raw_aggregate()` runs a native pipeline:

```python
await Article.query().raw_aggregate([
    {"$match": {"published": True}},
    {"$group": {"_id": "$author_id", "views": {"$sum": "$views"}}},
])
```

### What a store will not do

A document store has no joins, no `GROUP BY`, and no SQL to write. Rather than
quietly returning something else, those calls raise `UnsupportedQueryError`
and say what to reach for instead:

```python
Article.query().join("authors", ...)   # UnsupportedQueryError
Article.query().group_by("author_id")  # → use raw_aggregate()
Article.query().where_column("a", "b") # → use raw_aggregate() and $expr
```

## Relationships

References work unmodified, because a reference is a key lookup and a key
lookup does not care what stores the row. A document can point at another
document, or at a SQL model, in either direction:

```python
class Article(Document):
    @relation
    def author(self):
        return self.belongs_to(User, "author_id", "id")   # User is a SQL model
```

Eager loading, `with_count`, and lazy loading all work:

```python
await Article.query().with_("author").with_count("comments").get()
```

### Embedded documents

The relation SQL has no answer for is the child stored *inside* the parent.
An `EmbeddedDocument` has no key and no collection; it is a value with
behaviour:

```python
from almasix.orm import Document, EmbeddedDocument, relation


class Address(EmbeddedDocument):
    fields = ("city", "country")   # empty means anything goes


class Author(Document):
    @relation
    def address(self):
        return self.embeds_one(Address)

    @relation
    def tags(self):
        return self.embeds_many(Tag)
```

```python
await author.get_relation("address").create(city="Nairobi", country="KE")

address = author.get_relation("address").get()
address.city = "Mombasa"
await address.save()          # writes itself back into the parent document

tags = author.get_relation("tags")
await tags.create(name="math")
await tags.create_many([{"name": "engines"}])
tags.where(name="math")       # filtered in memory; they are already here
await tags.delete_where(name="math")
```

Both relations write the field on the parent, so an embed is saved by saving
the document it lives in — there is nowhere else for it to go.

## Indexes

A collection needs no migration; it appears on first write. Indexes are worth
declaring, and they live on the model:

```python
class Article(Document):
    indexes = (
        {"keys": [("slug", 1)], "unique": True},
        {"keys": [("author_id", 1), ("created_at", -1)], "name": "author_recent"},
    )
```

```bash
smith documents:index              # create them for every document model
smith documents:index --pretend    # say what would be created
smith documents:show               # collections, counts, and indexes
```

`await Article.sync_indexes()` does the same thing from code.

## Factories, soft deletes, and the rest

Nothing is special-cased. Add `HasFactory` and the factory writes documents;
add `SoftDeletes` and `deleted_at` filters the collection the same way it
filters a table:

```python
await Article.factory().count(3).create()
await article.delete()             # soft
await Article.with_trashed().count()
await article.force_delete()
```

## Generating one

```bash
smith make:document Article            # app/models/article.py
smith make:document Article --factory  # and database/factories/article_factory.py
smith make:document Address --embed    # an EmbeddedDocument
```

## Differences from Laravel

Laravel ships no NoSQL support, so this is Almasix's own surface. Two things
are worth naming for anyone arriving from `laravel-mongodb`:

- **Transactions.** Mongo transactions need a replica set, and Almasix does not
  pretend a single node has them. `DB.transaction()` covers SQL connections.
- **`_id` is a string.** Almasix hands back the store's key as it is, rather
  than wrapping it in an ObjectId type an application would then have to know
  about.
