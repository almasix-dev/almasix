---
title: Articulate — Getting Started
description: Define Active Record models and work with your database records.
---

**Articulate** is Avalon's Active Record ORM. Each database table has a corresponding model used to query and persist rows, with first-class `async`/`await`.

Every persistence and read method is **`await`ed** — Avalon is async-first for ASGI.

```python
# app/models/flight.py
from avalon.orm import Model, relation

class Flight(Model):
    fillable = ("name", "airline_id")

    @relation
    def airline(self):
        from app.models.airline import Airline
        return self.belongs_to(Airline)

flights = await Flight.query().with_("airline").where("active", True).get()
```

Generate a model (and optionally a migration) with Grail:

```bash
grail make:model Flight
grail make:model Flight -m
```

## Articulate model conventions

### Table names

By convention, the "snake case", plural name of the class is used as the table name — unless another name is explicitly specified. So `Flight` stores records in `flights`, and `BlogPost` in `blog_posts`. Override with:

```python
# app/models/flight.py
class Flight(Model):
    table = "my_flights"
```

### Primary keys

Articulate assumes each model has an auto-incrementing `id` primary key. Customize with `primary_key`, `incrementing`, and `key_type` as needed.

#### UUID and ULID keys

Mix in `HasUuids` for time-ordered (version 7) UUID keys, or `HasUlids` for 26-character ULIDs. Both turn off auto-increment, set `key_type = "string"`, and fill the key on insert:

```python
# app/models/article.py
from avalon.orm import HasUuids, Model


class Article(HasUuids, Model):
    fillable = ("title",)


article = await Article.create(title="Traveling to Europe")
article.id  # "0199c6f1-...", ordered by creation time
```

Mix them in **before** `Model`. Ordered UUIDs keep inserts local in the index, which is why they are the default rather than random v4. To generate ids yourself, or fill more than one column, override the hooks:

```python
class Article(HasUuids, Model):
    def new_unique_id(self) -> str:
        return my_own_generator()

    def unique_ids(self) -> tuple[str, ...]:
        return ("id", "public_id")
```

`ordered_uuid()` and `ulid()` are also importable from `avalon.orm` if you need a value outside a model.

### Timestamps

By default, Articulate expects `created_at` and `updated_at` columns. Set `timestamps = False` to skip automatic management. Call `await model.touch()` to update `updated_at` only.

To save without touching the timestamps just once, use the `without_timestamps` block. It is scoped to that model class, and `touch()` becomes a no-op inside it:

```python
with User.without_timestamps():
    user.name = "Ada"
    await user.save()
```

## Retrieving models

```python
# app/http/controllers/example_controller.py
await Flight.all()
await Flight.query().where("active", True).order_by("name").get()
await Flight.find(1)
await Flight.find_or_fail(1)       # raises ModelNotFoundError
await Flight.where("name", "Aurora").first()
```

`User.where(...)` is sugar for `User.query().where(...)`. Class-level `with_ = ("airline",)` eager-loads those relations on every `query()`; use `new_query()` to skip them.

## Inserting and updating

```python
# app/http/controllers/example_controller.py
flight = await Flight.create(name="Aurora", airline_id=1)
flight.name = "Northern Lights"
await flight.save()
await flight.update(name="Aurora")
await flight.refresh()
copy = flight.replicate()          # unsaved clone without id / timestamps
await Flight.destroy(1, 2, 3)
```

### Mass assignment

Models are guarded by default (`guarded = ("*",)`). List attributes in `fillable`, or use `force_fill` / `force_create`. Filling a totally guarded model raises `MassAssignmentError`.

For a block where the rules should not apply — seeding, for instance — unguard them:

```python
with Model.unguarded():
    await User.create(**untrusted)
```

`Model.unguard()` and `Model.reguard()` do the same thing without a block. Both are process-wide, so keep the window small.

### Strictness

Two checks are off by default because they are stricter than most apps want in production. Turn them on in a service provider, typically for local development only:

```python
# app/providers/app_service_provider.py
from avalon.orm import Model


class AppServiceProvider(ServiceProvider):
    def boot(self) -> None:
        Model.should_be_strict(self.app.environment("local"))
```

| Check | Effect |
| --- | --- |
| `prevent_silently_discarding_attributes()` | `fill()` raises `DiscardedAttributeError` instead of dropping a non-fillable key |
| `prevent_accessing_missing_attributes()` | Reading a column a persisted model never selected raises `MissingAttributeError` |
| `should_be_strict()` | Both of the above |

Lazy loading is already strict in Avalon: unloaded relation access raises unless you opt in, so there is no third switch.

Missing-attribute checks apply only to models that came from the database — a model you are still building reads as `None`. Pass a default to opt out for one read: `user.get_attribute("bio", "")`.

## Casts

```python
# app/models/user.py
class User(Model):
    fillable = ("email", "name", "votes")
    casts = {"votes": "int", "active": "bool", "meta": "json"}
    hidden = ("meta",)
```

Known cast names: `int`, `float`, `string`, `bool`, `decimal[:scale]`, `json` / `array` / `dict`, `date`, `datetime`, `time`, `timestamp`, `encrypted[:array]`, `hashed`, an `Enum` class, or a custom cast class.

### Accessors and mutators

```python
# app/models/user.py
from avalon.orm import Attribute

class User(Model):
    name = Attribute(get=lambda value: value.title(), set=lambda value: value.strip())
```

The `get_<name>_attribute` / `set_<name>_attribute` methods work too, and `appends = ("display",)` includes computed attributes in `to_dict()`.

See [Mutators & Casts](/articulate/casts/) for attribute objects, custom casts, encrypted and hashed casts, date formats, and query-time casting.

### Serialization visibility

`hidden` is a denylist and `visible` an allowlist, both declared on the model. To adjust them for a single record, use the instance methods — they affect **that model only**, never the class:

```python
user.make_hidden("email").to_dict()      # hide more on this record
user.make_visible("meta").to_dict()      # reveal a normally hidden attribute
user.set_hidden(["email"]).to_dict()     # replace the denylist outright
user.set_visible(["id", "name"]).to_dict()
```

Each returns the model, so they chain. Relation names may be hidden the same way.

## Quiet writes

Every write fires model events. To save, delete, or restore without them:

```python
await user.save_quietly()
await user.delete_quietly()
await user.force_delete_quietly()
await user.restore_quietly()      # SoftDeletes models
```

Quiet writes are scoped to that one instance, so a concurrent request keeps its own events. To mute a whole block, use `Model.without_events()`.

## Pruning models

Mix in `Prunable` and declare which rows are stale. `grail model:prune` deletes them:

```python
# app/models/flight.py
from avalon.orm import Model, Prunable


class Flight(Prunable, Model):
    def prunable(self):
        return self.query().where("created_at", "<", month_ago())

    async def pruning(self) -> None:
        """Called before each model is pruned — clean up related state here."""
        await self.storage_path().unlink()
```

`MassPrunable` deletes in bulk instead, which is far faster on large tables but skips `pruning()` since no models are loaded.

```bash
grail model:prune
grail model:prune --pretend            # report counts, delete nothing
grail model:prune --model=Flight
grail model:prune --except=Flight
grail model:prune --chunk=500
```

Models are discovered from `app/models`. Schedule it in `routes/console.py` to run daily — see [Task Scheduling](/scheduling/).

## Chunking large results

Loading a million rows into memory is how a worker dies. Four ways to avoid it:

```python
# One query per chunk, offset-paged.
await Flight.query().chunk(200, handle_chunk)

# One query per chunk, keyset-paged by id — safe when the callback writes.
await Flight.query().chunk_by_id(200, handle_chunk)
await Flight.query().each_by_id(handle_one)

# Async iteration, one row at a time, still one query per chunk.
async for flight in Flight.query().lazy(size=500):
    ...
async for flight in Flight.query().lazy_by_id(size=500):
    ...

# A single streamed result set — nothing but the current row in memory.
async for flight in Flight.query().cursor():
    ...
```

Prefer the `*_by_id` variants when the callback updates the column being ordered by: offset paging skips rows in that case, keyset paging does not. `cursor()` holds one result set open and therefore cannot apply eager loads.

## Dirty tracking

- `is_dirty("name")` / `is_clean()` / `get_dirty()` / `get_changes()` / `get_original("name")` / `was_changed("name")`
- `user.is_(other)` — same class and primary key
- `exists` — whether the model has been persisted
- `to_dict()` / `to_json()` honor `hidden`, `visible`, `appends`, and loaded relations — see [Serialization](/articulate/serialization/)

## Async & loading defaults

| Topic | Articulate behavior |
| --- | --- |
| Async | Every read/write is `await`ed |
| Relations | **Off by default** on attribute access. Unloaded `user.posts` raises. Opt in with `lazy_relations = True` so `await user.posts` loads; or use `with_` / `await user.posts().get()` |
| `where` | `where("col", val)` or `where("col", ">", val)` — two-arg form is **only** the `=` shortcut |
| Mass assignment | `MassAssignmentError` |
| Migrations | `grail migrate` |

:::tip[N+1 safety]
Failing loud on unloaded relations is the default. Prefer `with_` / `load` on list
endpoints. For awaitable late loading, set `lazy_relations = True` and
**await** the relation (`posts = await user.posts`) — never silent attribute IO.
:::

:::note[Coming from Eloquent?]
If you know Laravel Eloquent, Articulate will feel familiar — same Active Record shape, snake_case methods, and async throughout. The biggest habit change is **no silent lazy loading** unless you opt in.
:::

## Next steps

- [Relationships](/articulate/relationships/)
- [Mutators & Casts](/articulate/casts/)
- [Serialization](/articulate/serialization/)
- [Collections](/articulate/collections/)
- [Soft Deletes & Events](/articulate/events/)
- [Task Scheduling](/scheduling/) — for `model:prune`
- [Query Builder](/database/queries/)
