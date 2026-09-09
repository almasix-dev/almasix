---
title: Documents — Relationships & Embeds
description: Reference other models across SQL and document stores, or embed children inside a parent document.
---

## References

A reference is a key lookup. It does not care whether the related model lives
in a table or a collection, so the usual Articulate relations work unmodified:

```python
from almasix.orm import Document, relation
from app.models.user import User   # a SQL Model


class Article(Document):
    connection = "mongodb"

    @relation
    def author(self):
        return self.belongs_to(User, "author_id", "id")

    @relation
    def comments(self):
        return self.has_many(Comment, "article_id", "_id")
```

Eager loading, lazy loading, and relation counts work across the store
boundary:

```python
articles = await Article.query().with_("author").with_count("comments").get()
article = await Article.find(key)
author = await article.get_relation("author").get()
```

Document → document, document → SQL, and SQL → document are all valid as long
as the foreign key values match. There is no join under the hood: Almasix
loads the related keys in a second query, the same way it does for SQL eager
loads.

### Many-to-many and pivots

SQL `belongs_to_many` pivots do not exist on document stores. Do not fake a
pivot table against Mongo. Prefer:

- an array of related ids on the parent document, queried with `where_all` /
  `where` on that field, or
- a separate collection of edge documents you query explicitly.

Polymorphic relations that only need a type string + id work; pivot theater
does not.

## Embedded documents

The relation SQL has no answer for is the child stored *inside* the parent.
An `EmbeddedDocument` has no key and no collection of its own — it is a value
with behaviour:

```python
from almasix.orm import Document, EmbeddedDocument, relation


class Address(EmbeddedDocument):
    fields = ("city", "country", "postcode")
    # Leave fields empty to accept any attributes.


class Author(Document):
    @relation
    def address(self):
        return self.embeds_one(Address)

    @relation
    def tags(self):
        return self.embeds_many(Tag)
```

### embeds_one

```python
await author.get_relation("address").create(city="Nairobi", country="KE")

address = author.get_relation("address").get()
address.city = "Mombasa"
await address.save()   # writes itself back into the parent document

await author.get_relation("address").associate(Address(city="Kisumu", country="KE"))
await author.get_relation("address").delete()
```

### embeds_many

```python
tags = author.get_relation("tags")
await tags.create(name="math")
await tags.create_many([{"name": "engines"}, {"name": "docs"}])

matched = tags.where(name="math")          # filtered in memory; already loaded
await tags.delete_where(name="math")
```

Both relations write a field on the parent, so an embed is saved by saving the
document it lives in — there is nowhere else for it to go. Nested embeds are
plain attributes on the embedded class; keep the tree shallow enough that a
single document read stays useful.

## Choosing reference vs embed

| Prefer | When |
| --- | --- |
| **Embed** | The child is owned by the parent, loaded with it, and never queried alone |
| **Reference** | The related record has its own lifecycle, is shared, or lives in SQL |

Mixing both on one model is common: embed a location, reference a SQL user.
