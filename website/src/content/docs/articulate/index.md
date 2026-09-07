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

Articulate assumes each model has an `id` primary key. Customize with `primary_key` / `key_type` as needed.

### Timestamps

By default, Articulate expects `created_at` and `updated_at` columns. Set `timestamps = False` to skip automatic management. Call `await model.touch()` to update `updated_at` only.

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

## Casts

```python
# app/models/user.py
class User(Model):
    fillable = ("email", "name", "votes")
    casts = {"votes": "int", "active": "bool", "meta": "json"}
    hidden = ("meta",)
```

Known cast names: `int`, `float`, `string`, `bool`, `decimal[:scale]`, `json` / `array` / `dict`, `datetime`, `date`, `time`, `timestamp`, or an `Enum` class.

### Accessors and mutators

```python
# app/models/user.py
def get_display_attribute(self, value=None) -> str:
    return f"{self.name} <{self.email}>"

def set_name_attribute(self, value: str) -> str:
    return value.strip()
```

`appends = ("display",)` includes computed attributes in `to_dict()`.

### Serialization visibility

`hidden` is a denylist and `visible` an allowlist, both declared on the model. To adjust them for a single record, use the instance methods — they affect **that model only**, never the class:

```python
user.make_hidden("email").to_dict()      # hide more on this record
user.make_visible("meta").to_dict()      # reveal a normally hidden attribute
user.set_hidden(["email"]).to_dict()     # replace the denylist outright
user.set_visible(["id", "name"]).to_dict()
```

Each returns the model, so they chain. Relation names may be hidden the same way.

## Dirty tracking

- `is_dirty("name")` / `is_clean()` / `get_dirty()` / `get_changes()` / `get_original("name")` / `was_changed("name")`
- `user.is_(other)` — same class and primary key
- `exists` — whether the model has been persisted
- `to_dict()` / `to_json()` honor `hidden`, `visible`, `appends`, and loaded relations

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
- [Collections](/articulate/collections/)
- [Soft Deletes & Events](/articulate/events/)
- [Query Builder](/database/queries/)
