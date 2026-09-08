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

### Querying relationship existence

```python
# app/http/controllers/example_controller.py
await User.query().has("posts", ">=", 2).get()
await User.query().doesnt_have("posts").get()
await User.query().where_has(
    "posts", lambda q: q.where("published", True)
).get()
await User.query().where_doesnt_have("posts").get()
```

## Soft deletes on related models

When a related model uses soft deletes, put the mixin **before** `Model` so the global scope registers correctly:

```python
# app/models/post.py
class Post(SoftDeletes, Model):
    ...
```
