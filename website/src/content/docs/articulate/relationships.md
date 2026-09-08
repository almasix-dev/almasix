---
title: Relationships
description: Define and eager-load Articulate relationships.
---

Database tables are often related to one another. For example, a blog post may have many comments, or an order may belong to a user. Articulate makes managing and working with these relationships easy.

Declare relationships with `@relation`. Calling the method (`user.posts()`) returns the relation object so you can keep querying. Reading the attribute (`user.posts`) returns **already loaded** data only.

```python
# app/models/user.py
from avalon.orm import Model, relation, RelationNotLoadedError

class User(Model):
    @relation
    def posts(self):
        return self.has_many(Post)

    @relation
    def roles(self):
        return self.belongs_to_many(Role).with_pivot("level")

# Query through the relationship
posts = await user.posts().where("published", True).get()

# Unloaded attribute access does not hit the database
try:
    len(user.posts)
except RelationNotLoadedError:
    pass

# Opt-in awaitable lazy load (explicit await — still no silent IO)
class LazyUser(User):
    lazy_relations = True

user = await LazyUser.find(1)
posts = await user.posts
```

:::caution
By default Avalon does **not** lazy-load on attribute access. A hidden query there is how N+1 problems start. Eager-load with `with_`, query with `await user.posts().get()`, or set `lazy_relations = True` and use `await user.posts`.
:::


## Defining relationships

| Method | Role |
| --- | --- |
| `has_one` / `has_many` | One-to-one / one-to-many |
| `belongs_to` | Inverse of has-one/has-many (`associate` / `dissociate`) |
| `belongs_to_many` | Many-to-many + pivot |
| `has_one_through` / `has_many_through` | Distant one-to-one / one-to-many via an intermediate |
| `morph_one` / `morph_many` | Polymorphic one-to-one / one-to-many |
| `morph_to(name, types={…})` | Inverse polymorphic — pass the type map |
| `morph_to_many` / `morphed_by_many` | Polymorphic many-to-many |

Has-many helpers: `create`, `save`, `save_many`, `create_many`, `first_or_create`.

Belongs-to-many: `attach`, `detach`, `sync`, `toggle`, `update_existing_pivot`, `where_pivot`, `with_pivot`.

## Has one of many

A user has many orders, but you often want exactly one of them — the latest, or
the most expensive. Narrow a has-many with `latest_of_many`, `oldest_of_many`, or
`of_many`:

```python
# app/models/user.py
class User(Model):
    @relation
    def latest_order(self):
        return self.has_many(Order).latest_of_many()

    @relation
    def oldest_order(self):
        return self.has_many(Order).oldest_of_many()

    @relation
    def largest_order(self):
        return self.has_many(Order).of_many("price", "max")
```

`latest_of_many` and `oldest_of_many` sort on the primary key unless you name a
column, so `latest_of_many("published_at")` works too. These are real has-one
relations: read them with `await user.latest_order().get()`, or eager-load them
with `User.with_relations("latest_order")` and get one row per user from one
query rather than every order.

Break ties by passing a mapping, and constrain the candidates with a callback:

```python
# The newest of the highest-priced orders.
return self.has_many(Order).of_many({"price": "max", "id": "max"})

# The largest order that was actually published.
return self.has_many(Order).of_many(
    "price", "max", lambda query: query.where("published", "=", True)
)
```

`one()` converts a many relation to a has-one without an aggregate, which is
what `of_many` builds on. Morph relations support the same calls, so
`self.morph_many(Comment, "commentable").latest_of_many()` stays polymorphic.

## Default models

`belongs_to`, `has_one`, and `morph_one` return `None` when nothing is related,
which pushes a `None` check into every template. `with_default` returns an
unsaved placeholder model instead:

```python
# app/models/post.py
class Post(Model):
    @relation
    def author(self):
        return self.belongs_to(User).with_default({"name": "Guest Author"})
```

Pass nothing for an empty model, a mapping to seed attributes, or a callable
taking the default instance and the parent:

```python
return self.belongs_to(User).with_default(
    lambda default, post: default.force_fill({"name": f"Author of {post.title}"})
)
```

The default is never persisted — `default.exists` is `False` — and it applies to
eager loads as well as direct reads.

## Chaperone

Iterating a parent's children and reading the child's parent relation raises,
because that relation was never loaded — even though the parent is the model you
already have. `chaperone()` hydrates it:

```python
# app/models/post.py
class Post(Model):
    @relation
    def comments(self):
        return self.has_many(Comment).chaperone()
```

Now `post.comments[0].post` is the same `post` object, with no second query.
Avalon guesses the inverse relation from the parent class name; pass the name
explicitly when it differs, as in `chaperone("article")`. It works on
`has_many`, `has_one`, `morph_many`, and `morph_one`.

## Eager loading

```python
# app/http/controllers/example_controller.py
posts = await Post.query().with_("author").get()
posts[0].author.name

users = await User.query().with_(
    "posts",
    notes=lambda q: q.where("published", True),
).get()

await User.query().with_("posts.comments").get()
await User.query().with_count("posts").get()
user._extra["posts_count"]

await user.load("posts")
await user.load_missing("profile")
await users.load("posts")   # Collection
```

## Aggregating related models

Counting or summing a relation does not need the related rows loaded. Each
aggregate runs one extra query for the whole result set and lands on the parent
under a conventional name:

```python
writers = await Writer.query().with_count("entries").get()
writers[0].entries_count            # 2

writers = await (
    Writer.query()
    .with_sum("entries", "votes")   # entries_sum_votes
    .with_avg("entries", "votes")   # entries_avg_votes
    .with_min("entries", "votes")   # entries_min_votes
    .with_max("entries", "votes")   # entries_max_votes
    .with_exists("entries")         # entries_exists -> bool
    .get()
)
```

A relation with no rows counts `0` and exists `False`; the column aggregates are
`None`, matching Laravel's null.

Constrain an aggregate with a keyword callback, and rename it with `as`:

```python
await Writer.query().with_count(
    entries=lambda q: q.where("published", "=", True)
).get()

await Writer.query().with_count({
    "entries as published_count": lambda q: q.where("published", "=", True)
}).get()
```

`with_aggregate("entries", "sum", "votes", "score")` is the long form when you
want to name both the function and the attribute yourself. Aggregates are
independent of `select`, so narrowing the parent's columns does not drop them.

### Deferred aggregates

When the parents are already in hand, the `load_` family does the same work:

```python
await writer.load_count("entries")
await writer.load_sum("entries", "votes")
await writer.load_exists("entries")
await writer.load_aggregate("entries", "votes", "max")

writers = await Writer.query().get()
await writers.load_count("entries")   # one query for the whole collection
```

These take the same callbacks, mappings, and `as` aliases as their eager twins.

## Querying relationship existence

```python
# app/http/controllers/example_controller.py
await User.query().has("posts", ">=", 2).get()
await User.query().doesnt_have("posts").get()
await User.query().where_has(
    "posts", lambda q: q.where("published", True)
).get()
await User.query().where_doesnt_have("posts").get()
```

Each of these has an `or_` twin — `or_has`, `or_doesnt_have`, `or_where_has`,
`or_where_doesnt_have` — that joins the clause with `OR` instead of `AND`:

```python
await User.query().where("country", "=", "US").or_has("posts").get()
```

Dots walk nested relations. The count and the callback apply to the innermost
relation, so this finds users with a post that has at least one comment:

```python
await User.query().has("posts.comments").get()
await User.query().where_has(
    "posts.comments", lambda q: q.where("approved", "=", True)
).get()
```

### Inline existence queries

When the constraint is a single simple condition, `where_relation` saves the
closure:

```python
await User.query().where_relation("posts", "published", False).get()
await User.query().where_relation("posts", "views", ">", 1000).get()
```

`or_where_relation` is the `OR` form.

### Filtering and loading in one call

`with_where_has` filters parents by a relation *and* eager-loads that relation
under the same constraint, so the loaded children match what you filtered on:

```python
users = await User.query().with_where_has(
    "posts", lambda q: q.where("published", "=", True)
).get()

users[0].posts   # published posts only
```

### Morph to existence

`morph_to` relations query across their possible types. Pass model classes, type
aliases, a mapping, or `"*"` for every mapped type:

```python
# Comments left on articles.
await Comment.query().where_has_morph("commentable", [Article]).get()

# Every mapped type, with the type name handed to the callback.
await Comment.query().where_has_morph(
    "commentable",
    "*",
    lambda query, morph_type: query.where("title", "like", "Laravel%")
    if morph_type is Article
    else query,
).get()
```

The callback may take just the query if it does not care about the type. The
full set is `has_morph`, `or_has_morph`, `doesnt_have_morph`,
`or_doesnt_have_morph`, `where_has_morph`, `or_where_has_morph`,
`where_doesnt_have_morph`, `or_where_doesnt_have_morph`, plus the inline
`where_morph_relation` and `or_where_morph_relation`.

`doesnt_have_morph` with no callback is how you find orphaned rows — comments
whose `commentable_id` points at nothing.

## Soft deletes on related models

When a related model uses soft deletes, put the mixin **before** `Model` so the global scope registers correctly:

```python
# app/models/post.py
class Post(SoftDeletes, Model):
    ...
```
