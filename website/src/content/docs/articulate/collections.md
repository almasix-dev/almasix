---
title: Collections
description: Work with Articulate collections returned from queries.
---

All multi-result sets returned by Articulate are instances of `almasix.orm.Collection`, including results retrieved via the `get` method or accessed via a relationship. The Articulate collection object extends Python list semantics and provides many helpful methods for working with your results.

```python
# app/http/controllers/example_controller.py
from almasix.orm import Collection

users = await User.query().order_by("id").get()
users.first()
users.pluck("email")
users.where("name", "Ada")
users.filter(lambda u: u.votes > 3)
await users.load("posts")
users.to_dict()
```

## Available methods

**Container:** `len`, iterate, index, slice (returns a `Collection`), `bool`, equality with list/`Collection`.

**Access:** `all`, `first`, `last`, `is_empty`, `is_not_empty`, `count`.

**Transform:** `map`, `filter` (truthy if no callback), `reject`, `where`, `where_in`, `first_where`, `pluck` (optional index key → dict), `unique`, `sort_by` / `sort_by_desc`, `group_by`, `key_by`, `chunk`, `take`, `skip`, `each`, `contains`, `sum` / `avg` / `max` / `min`, `push`, `merge`, `reverse`, `values`.

**Models:** `model_keys`, `to_dict`, `load`, `load_missing`, `find`, `fresh`, `to_query`.

**Serialization:** `make_hidden`, `make_visible`, `set_hidden`, `set_visible`, `append` — each applies to every model in the collection.

`where` on a Collection is **in-memory** (`item[key] == value`), not a SQL builder.

## Keyed by the model, not the index

Several inherited methods are overridden to work on the models' primary keys, matching Eloquent:

```python
users.find(1)                    # the model whose key is 1
users.find(other_model)          # by another model's key
users.contains(1)                # membership by key, model, or callback

users.only([1, 2])               # keep these keys
users.except_([1])               # drop these keys
users.diff(others)               # models not present in `others`
users.intersect(others)          # models present in both
users.unique()                   # deduplicate by primary key
```

`unique("name")` still deduplicates by an attribute when you pass one.

## Reloading and re-querying

`fresh` reloads every model from the database, dropping any that no longer exist. It accepts relations to eager-load:

```python
users = await users.fresh()
users = await users.fresh("posts")
```

`to_query` returns a query builder constrained to the collection's models, which is how you turn a loaded set back into a query:

```python
await users.to_query().update({"active": True})
```

It raises `ValueError` on an empty collection, since there would be nothing to constrain.

## Custom collections

To return your own collection type from a model, set `collection_class`:

```python
from almasix.orm import Collection, Model


class UserCollection(Collection):
    def admins(self) -> "UserCollection":
        return self.filter(lambda user: user.is_admin)


class User(Model):
    collection_class = UserCollection
```

Every multi-row read on that model — including relations — now returns a `UserCollection`. `User.new_collection([...])` builds one directly.

## Paginating results

For length-aware and simple pagination, see [Pagination](/database/pagination/).
