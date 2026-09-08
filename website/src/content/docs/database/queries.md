---
title: Query Builder
description: Build fluent, database-agnostic queries with Almasix's query builder.
---

Almasix's database query builder provides a convenient, fluent interface for creating and running database queries. It can be used to perform most database operations in your application and works with every supported database driver.

Start from a Articulate model (`User.query()`) or a table (`DB.table("users")`).

## Introduction to `where` clauses

**Canonical form:** `where("column", operator, value)`  
**Shortcut:** `where("column", value)` assumes the `=` operator.

The shortcut never inspects the second argument. `where("op", ">")` means `op = '>'` — not a comparison operator.

```python
# app/http/controllers/example_controller.py
await Item.query().where("votes", ">", 4).get()
await Item.query().where("name", "beta").first()   # name = 'beta'
await Item.query().where("op", ">").first()        # op = '>'
await Item.query().where(
    lambda q: q.where("votes", ">=", 5).where("name", "!=", "gamma")
).first()
```

The same two-argument / three-argument split applies to `or_where`, `having`, `where_column`, `join`, and `where_pivot`.

Supported operators: `=`, `==`, `!=`, `<>`, `>`, `>=`, `<`, `<=`, `like`, `not like`, `ilike`, `not ilike`, `in`, `not in`.

### Additional where clauses

| Method | Notes |
| --- | --- |
| `where` / `or_where` | Column comparison or nested closure |
| `where_in` / `or_where_in` / `where_not_in` | |
| `where_null` / `or_where_null` / `where_not_null` / `or_where_not_null` | Prefer these over `where("col", None)` |
| `where_between` / `where_not_between` | |
| `where_column` | Compare two columns; two-arg form is `=` |
| `where_like` | |
| `where_year` / `where_month` / `where_day` / `where_date` | |
| `where_raw` | Raw SQL fragment |

## Selects, ordering, and aggregates

Available methods include `select`, `add_select`, `select_raw`, `distinct`, `order_by` / `order_by_desc`, `latest` / `oldest`, `in_random_order`, `reorder`, `group_by`, `having` / `having_raw`, `limit`/`take`, `offset`/`skip`, and `for_page`.

Aggregates: `count`, `sum`, `avg`, `max`, `min`, `value`, `pluck`, `exists`, `doesnt_exist`.

```python
# app/http/controllers/example_controller.py
name = await User.query().where("votes", ">=", 5).value("name")
names = await User.query().order_by("name").pluck("name")
sql = User.query().where("email", "like", "%@example.com").to_sql()
```

## Joins and conditional clauses

```python
# app/http/controllers/example_controller.py
User.query().join("posts", "users.id", "posts.user_id")
User.query().left_join("profiles", "users.id", "=", "profiles.user_id")
User.query().when(active, lambda q: q.where("active", True))
User.query().unless(admin, lambda q: q.where("role", "user"))
User.query().tap(lambda q: print(q.to_sql()))
```

`cross_join` and `right_join` are available. RIGHT JOIN requires SQLite **3.39+**; PostgreSQL and MySQL support it natively.

## Inserts, updates, and deletes

`insert`, `insert_get_id`, `update`, `delete`, `increment`, `decrement`, `upsert`, `first_or_create`, `first_or_new`, and `update_or_create` are all available.

### Upserts

`upsert` uses dialect-native SQL when possible:

| Dialect | Construct |
| --- | --- |
| SQLite / PostgreSQL | `INSERT … ON CONFLICT (unique_by) DO UPDATE` |
| MySQL | `INSERT … ON DUPLICATE KEY UPDATE` |
| Other | Probe-then-write fallback |

```python
# app/http/controllers/example_controller.py
await User.query().upsert(
    {"email": "a@b.c", "name": "Updated"},
    unique_by=["email"],
    update=["name"],
)
```

:::caution
Columns listed in `unique_by` must have a UNIQUE index or constraint. An empty `update` list means “do nothing on conflict” (SQLite/PostgreSQL) or a no-op assignment (MySQL).
:::


## Chunking results

```python
# app/http/controllers/example_controller.py
await User.query().order_by("id").chunk(100, lambda rows: ...)
await User.query().each(lambda user: ..., size=100)
async for user in User.query().cursor(size=100):
    ...
```

Callbacks may be async. Return `False` from a callback to stop iteration.

`to_sql()` compiles with literal binds when possible and still works if no connection is available yet.
