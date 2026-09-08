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

## Many to many: the intermediate table

Rows from a many-to-many relation carry their pivot row with them:

```python
# app/models/user.py
class User(Model):
    @relation
    def plans(self):
        return self.belongs_to_many(Plan).with_pivot("tier")
```

```python
for plan in await user.plans().get():
    plan.pivot.tier
```

`with_pivot` names the extra columns to fetch. `as_("subscription")` renames the
accessor, so the same row reads as `plan.subscription.tier` — worth doing when
"pivot" says nothing about the domain.

`with_timestamps()` maintains `created_at` and `updated_at` on the intermediate
table: attaching stamps both, and `update_existing_pivot` bumps `updated_at`.

### Custom intermediate models

`using()` hydrates pivot rows into a `Pivot` subclass, which can carry accessors,
casts, and methods of its own:

```python
# app/models/subscription.py
from avalon.orm import Pivot

class Subscription(Pivot):
    casts = {"tier": "string", "started_at": "datetime"}

    @property
    def is_premium(self) -> bool:
        return self.tier == "gold"
```

```python
return self.belongs_to_many(Plan).using(Subscription).as_("subscription")
```

Pivot instances save and delete through their relation, so
`await plan.pivot.save()` writes just the intermediate row.

### Filtering and ordering on pivot columns

```python
await user.plans().where_pivot("tier", "=", "gold").get()
await user.plans().where_pivot_in("tier", ["gold", "silver"]).get()
await user.plans().where_pivot_not_in("tier", ["free"]).get()
await user.plans().where_pivot_null("cancelled_at").get()
await user.plans().where_pivot_not_null("cancelled_at").get()
await user.plans().where_pivot_between("seats", 5, 50).get()
await user.plans().order_by_pivot("created_at", "desc").get()
```

These constraints belong to the relation, so they apply to eager loads as well
as direct reads.

### Attaching, syncing, toggling

```python
await user.plans().attach(plan.id, {"tier": "gold"})
await user.plans().attach({1: {"tier": "gold"}, 2: {"tier": "free"}})
await user.plans().detach([1, 2])
await user.plans().detach()            # everything

await user.plans().sync([1, 2, 3])
await user.plans().sync({1: {"tier": "gold"}})
await user.plans().sync_without_detaching([4])
await user.plans().toggle([1, 2])
await user.plans().update_existing_pivot(1, {"tier": "silver"})
```

`sync` reports what changed as `{"attached": [...], "detached": [...],
"updated": [...]}`. Ids that were already attached but whose pivot attributes
changed land under `updated`.

## Custom polymorphic types

By default a `*_type` column stores the model's class name, which welds the
database to the code layout — rename or move a class and the stored rows stop
resolving. Register a morph map instead, usually in a service provider:

```python
# app/providers/app_service_provider.py
from avalon.orm import morph_map

class AppServiceProvider(ServiceProvider):
    def boot(self) -> None:
        morph_map({
            "post": Post,
            "video": Video,
        })
```

Now `commentable_type` holds `"post"`, and `morph_to` resolves it without an
explicit type map:

```python
# app/models/comment.py
@relation
def commentable(self):
    return self.morph_to("commentable")   # uses the registered map
```

`enforce_morph_map({...})` goes further and raises for any polymorphic model
missing from the map, which is how you keep class names from leaking into new
tables. A row whose type column is empty resolves to `None`; a stored type the
map does not know is an error.

## Dynamic relationships

A package can relate your models to its own without editing them:

```python
# app/providers/app_service_provider.py
User.resolve_relation_using("subscription", lambda user: user.has_one(Subscription))
```

The relation then behaves like a declared one: `user.subscription()` queries it,
`with_("subscription")` loads it, and reading it unloaded still raises.

## Querying a relationship's parent

When you already hold the parent, `where_belongs_to` reads better than digging
out its key. The relation is guessed from the parent's class:

```python
await Post.query().where_belongs_to(user).get()
await Post.query().where_belongs_to(user, "author").get()   # name it explicitly
```

Pass a collection or list to match any of several parents, and use
`or_where_belongs_to` for the `OR` form.

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

## Eager loading

Reading a relation you did not load raises rather than quietly running a query,
so eager loading is not an optimisation here — it is how you get the data:

```python
# app/http/controllers/example_controller.py
posts = await Post.query().with_("author").get()
posts[0].author.name
```

That is one query for the posts and one for their authors, whatever the row
count.

### Multiple, nested, and constrained

```python
await User.query().with_("posts", "profile").get()
await User.query().with_("posts.comments").get()          # nested

await User.query().with_(
    "posts",
    notes=lambda q: q.where("published", True),           # constrained
).get()
```

A keyword callback receives the relation's query builder, so it can filter,
order, or narrow the selected columns. `without("posts")` drops a relation that
an earlier scope added.

### Lazy eager loading

When the parents are already loaded, `load` fills relations in afterwards:

```python
await user.load("posts")
await user.load_missing("profile")     # skips what is already loaded
await users.load("posts")              # a whole Collection, still one query
```

### Eager loading by default

A relation that every read needs can be declared on the model, so it loads on
each `query()` without being asked for:

```python
class Post(Model):
    with_ = ("author",)
```

`new_query()` skips the defaults for the rare read that does not want them, and
`without("author")` drops one of them from a query you are already building.

### Behind a morph to

A `morph_to` points at a different class on each row, so one relation list
cannot fit them all. `load_morph` takes a relation per target class:

```python
comments = await Comment.query().get()

await comments.load_morph("commentable", {
    Post: ["author"],
    Video: ["channel"],
})

await comments.load_morph_count("commentable", {
    Post: ["comments"],
    Video: ["clips"],
})
```

Types you leave out of the mapping are loaded as-is. Both methods also work on
a single model. String class names work in place of the classes themselves.

### Preventing N+1 by default

Laravel lazy-loads on property access and offers `preventLazyLoading()` to turn
that off. Avalon inverts the default deliberately: property access on an
unloaded relation raises `RelationNotLoadedError`, because a hidden query behind
an attribute read is exactly how N+1 problems reach production unnoticed.

If you want Laravel's behaviour on a given model, opt in explicitly — the query
is still awaited, so the IO stays visible:

```python
class User(Model):
    lazy_relations = True

posts = await user.posts          # awaited, not hidden
```

## Inserting and updating related models

```python
await post.comments().create({"body": "Nice"})
await post.comments().create_many([{"body": "One"}, {"body": "Two"}])
await post.comments().create_quietly({"body": "No events"})
await post.comments().save(comment)
await post.comments().save_many([first, second])

comment = post.comments().make({"body": "Unsaved"})       # foreign key set
comments = post.comments().make_many([{"body": "a"}])

await post.comments().first_or_create({"body": "Nice"})
await post.comments().first_or_new({"body": "Nice"})
await post.comments().find_or_new(comment_id)
await post.comments().update_or_create({"body": "old"}, {"body": "new"})
```

`associate` and `dissociate` set and clear the foreign key on a `belongs_to`
child.

### Saving a whole graph

`push` saves the model and every relation already loaded on it, however deep:

```python
post = await Post.query().with_("comments.author").first()
post.title = "Edited"
post.comments[0].body = "Also edited"

await post.push()          # post, comments, and their authors
```

It stops and returns `False` as soon as a save is cancelled by a `saving`
listener. Relations that hold each other — a chaperoned child pointing back at
its parent — are saved once rather than walked in circles.


## Touching parent timestamps

When a child changes, the parent's `updated_at` often should change too — a
cached post listing goes stale when a comment is edited. Name the relations to
bump:

```python
# app/models/comment.py
class Comment(Model):
    touches = ("post",)

    @relation
    def post(self):
        return self.belongs_to(Post)
```

Saving a comment now touches its post. Suspend it with
`Model.without_touching()`, or for particular models with
`Model.without_touching_on(Comment)`.

## Soft deletes on related models

When a related model uses soft deletes, put the mixin **before** `Model` so the global scope registers correctly:

```python
# app/models/post.py
class Post(SoftDeletes, Model):
    ...
```

## Not shipped yet

Two things on Laravel's page are deliberately absent:

- **Scoped relationships** (`withAttributes`), which push a relation's
  constraints into the models it creates, land with the subquery work in M42.
- **Automatic eager loading** (`automaticallyEagerLoadRelationships`) has no
  counterpart, because Avalon does not lazy-load in the first place — see
  [preventing N+1 by default](#preventing-n1-by-default).
