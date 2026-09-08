---
title: Query Builder
description: A fluent interface for reading and writing rows — wheres, joins, unions, locking, and everything Laravel's query builder spells, awaited.
---

## Introduction

The query builder is a fluent interface for most of the database work an
application does. It runs on every supported driver, and it never puts your
values into the SQL string: bindings go to the driver, so a query is safe to
build from user input.

Start from a table for rows, or from an [Articulate model](/articulate/) for
models:

```python
from almasix.orm import DB

rows = await DB.table("users").where("votes", ">", 100).get()
users = await User.query().where("votes", ">", 100).get()
```

Nothing runs until you await something. `get`, `first`, `count`, `update` and
their kind are the coroutines; everything else builds.

## Running database queries

### Retrieving all rows

`get` returns a [collection](/collections/) — of dictionaries from a table, of
models from a model:

```python
users = await DB.table("users").get()

for user in users:
    print(user["name"])
```

### Retrieving a single row or column

```python
user = await DB.table("users").where("name", "Ada").first()
user = await DB.table("users").where("name", "Ada").first_or_fail()
user = await DB.table("users").where("name", "Ada").sole()
user = await DB.table("users").find(3)

email = await DB.table("users").where("name", "Ada").value("email")
```

`sole` insists on exactly one row: no rows raises `ModelNotFoundError`, and
more than one raises `MultipleRecordsFoundError`.

### Retrieving a list of column values

```python
titles = await DB.table("roles").pluck("title")
titles = await DB.table("roles").pluck("title", "name")   # keyed by name
names = await DB.table("users").implode("name", ", ")     # one joined string
```

### Chunking results

Thousands of rows do not have to be in memory at once. `chunk` reads a page at
a time and hands each page to a callback; returning `False` stops it:

```python
await DB.table("users").order_by("id").chunk(100, handle_page)

async def handle_page(users):
    for user in users:
        ...
```

When the callback updates the rows it is reading, order by the primary key and
use `chunk_by_id`, which pages by the last id seen rather than by offset — an
updated row can otherwise slide out from under the paging:

```python
await DB.table("users").where("active", False).chunk_by_id(100, activate)
await DB.table("users").each(send_reminder, size=200)
```

### Streaming results lazily

`lazy` gives back a lazy collection that reads a chunk at a time as it is
iterated, so the whole set is never in memory:

```python
async for user in DB.table("users").order_by("id").lazy():
    ...

async for user in DB.table("users").lazy_by_id(500):
    ...
```

`cursor` is the same idea with the driver doing the buffering.

### Aggregates

```python
count = await DB.table("users").count()
price = await DB.table("orders").max("price")
average = await DB.table("orders").where("finalized", True).avg("price")
total = await DB.table("orders").sum("price")
```

`average` is spelled both ways, as it is in Laravel.

### Determining if records exist

```python
if await DB.table("orders").where("finalized", True).exists():
    ...

if await DB.table("orders").where("finalized", True).doesnt_exist():
    ...
```

## Select statements

```python
users = await DB.table("users").select("name", "email as user_email").get()
users = await DB.table("users").distinct().get()

query = DB.table("users").select("name")
users = await query.add_select("age").get()
```

## Raw expressions

`DB.raw` and `select_raw` drop a fragment straight into the statement. They are
never escaped, so keep user input out of them and pass it as a binding
instead:

```python
await DB.table("users").select_raw("count(*) as user_count, status").group_by("status").get()

await DB.table("orders").where_raw("price > IF(state = 'TX', :low, :high)", {"low": 200, "high": 100}).get()

await DB.table("orders").having_raw("SUM(price) > 2500").group_by("department").get()

await DB.table("orders").order_by_raw("updated_at - created_at DESC").get()

await DB.table("orders").select("department").group_by_raw("department, status").get()
```

## Joins

### Inner and outer joins

```python
await (
    DB.table("users")
    .join("contacts", "users.id", "=", "contacts.user_id")
    .join("orders", "users.id", "=", "orders.user_id")
    .select("users.*", "contacts.phone", "orders.price")
    .get()
)

DB.table("users").left_join("posts", "users.id", "=", "posts.user_id")
DB.table("users").right_join("posts", "users.id", "=", "posts.user_id")
DB.table("sizes").cross_join("colors")
```

A right join is compiled as the left join that returns the same rows, so it
works on every engine — including SQLite builds older than 3.39.

### Advanced join clauses

Pass a callable instead of a column and it receives a join clause, which takes
`on`, `or_on`, and the whole `where` family:

```python
DB.table("users").join(
    "contacts",
    lambda join: join.on("users.id", "=", "contacts.user_id").where("contacts.user_id", ">", 5),
)

DB.table("users").join(
    "contacts",
    lambda join: join.on("users.id", "=", "contacts.user_id").or_on(
        "users.id", "=", "contacts.proxy_id"
    ),
)
```

### Subquery joins

`join_sub`, `left_join_sub`, `right_join_sub`, and `cross_join_sub` join a
query under a name:

```python
latest = (
    DB.table("posts")
    .select("user_id")
    .select_raw("MAX(created_at) as last_post_created_at")
    .group_by("user_id")
)

await (
    DB.table("users")
    .join_sub(latest, "latest_posts", "users.id", "=", "latest_posts.user_id")
    .get()
)
```

### Lateral joins

A lateral join lets the subquery read the row it is joined to, so "the three
newest posts for each user" is one query. PostgreSQL, MySQL 8.0.14+, and SQL
Server support it:

```python
latest = (
    DB.table("posts")
    .select("body")
    .where_column("posts.user_id", "users.id")
    .order_by_desc("created_at")
    .limit(3)
)

await DB.table("users").left_join_lateral(latest, "latest_posts").get()
```

## Unions

```python
first = DB.table("users").where_null("first_name")
users = await DB.table("users").where_null("last_name").union(first).get()
```

`union_all` keeps the duplicates a union drops. Ordering and paging asked for
after a union apply to the combined result, as they do in Laravel.

## Basic where clauses

The canonical form is `where(column, operator, value)`. The two-argument form
means `=`, and it never guesses: `where("op", ">")` is `op = '>'`.

```python
await DB.table("users").where("votes", "=", 100).get()
await DB.table("users").where("votes", 100).get()
await DB.table("users").where("votes", ">=", 100).where("name", "like", "T%").get()
```

Operators: `=`, `==`, `!=`, `<>`, `>`, `>=`, `<`, `<=`, `like`, `not like`,
`ilike`, `not ilike`, `in`, `not in`. Anything else is refused rather than
passed through.

### Or where clauses

Every `where` has an `or_where` twin. Group what should be grouped by passing a
callable — `or_where` with a group keeps the parentheses where you meant them:

```python
await (
    DB.table("users")
    .where("votes", ">", 100)
    .or_where(lambda query: query.where("name", "Abigail").where("votes", ">", 50))
    .get()
)
```

### Where not clauses

`where_not` negates a whole group:

```python
await (
    DB.table("products")
    .where_not(lambda query: query.where("clearance", True).or_where("price", "<", 10))
    .get()
)
```

### Where any / all / none clauses

The same condition against several columns:

```python
await DB.table("users").where_any(["name", "email", "phone"], "like", "Example%").get()
await DB.table("users").where_all(["name", "email"], "like", "Example%").get()
await DB.table("users").where_none(["name", "email"], "like", "Example%").get()
```

### JSON where clauses

Reach inside a JSON column with Laravel's arrow syntax. MySQL 8+, PostgreSQL,
SQLite 3.39+, and SQL Server 2016+ can all read it:

```python
await DB.table("users").where("preferences->dining->meal", "salad").get()

await DB.table("users").where_json_contains("options->languages", "en").get()
await DB.table("users").where_json_doesnt_contain("options->languages", "en").get()
await DB.table("users").where_json_contains_key("preferences->dining->meal").get()
await DB.table("users").where_json_length("options->languages", ">", 1).get()
```

### Additional where clauses

| Method | What it matches |
| --- | --- |
| `where_between` / `where_not_between` | A value within (or outside) two bounds |
| `where_between_columns` / `where_not_between_columns` | A column between two other columns |
| `where_value_between` / `where_value_not_between` | A value between two columns |
| `where_in` / `where_not_in` | A list, or a subquery |
| `where_integer_in_raw` / `where_integer_not_in_raw` | A large list of integers, inlined rather than bound |
| `where_null` / `where_not_null` | Prefer these to `where(column, None)` |
| `where_null_safe_equals` | Equality that counts two nulls as equal |
| `where_date` / `where_month` / `where_day` / `where_year` / `where_time` | One part of a timestamp |
| `where_past` / `where_future` / `where_now_or_past` / `where_now_or_future` | A timestamp against now |
| `where_today` / `where_before_today` / `where_after_today` / `where_today_or_before` / `where_today_or_after` | A timestamp against today |
| `where_column` | One column against another |
| `where_like` / `where_not_like` | A pattern, optionally `case_sensitive=True` |
| `where_belongs_to` | Rows belonging to a model instance |

```python
await DB.table("users").where_between("votes", [1, 100]).get()
await DB.table("users").where_in("id", [1, 2, 3]).get()
await DB.table("users").where_in("id", DB.table("comments").select("user_id")).get()
await DB.table("users").where_null("updated_at").get()
await DB.table("users").where_date("created_at", "2016-12-31").get()
await DB.table("invoices").where_past("due_at").get()
await DB.table("users").where_column("updated_at", ">", "created_at").get()
await DB.table("users").where_like("name", "%Ada%", case_sensitive=True).get()
```

Case sensitivity is the one thing engines disagree about: MySQL gets
`LIKE BINARY`, and everyone else already compares byte for byte.

### Logical grouping

A callable is a parenthesised group:

```python
await (
    DB.table("users")
    .where("name", "=", "John")
    .where(lambda query: query.where("votes", ">", 100).or_where("title", "=", "Admin"))
    .get()
)
```

## Advanced where clauses

### Where exists clauses

```python
await (
    DB.table("users")
    .where_exists(
        DB.table("orders").select_raw(1).where_column("orders.user_id", "users.id")
    )
    .get()
)
```

`where_not_exists` is the negation.

### Subquery where clauses

A subquery may stand on either side of a comparison:

```python
await (
    DB.table("users")
    .where(
        DB.table("memberships")
        .select("type")
        .where_column("memberships.user_id", "users.id")
        .order_by_desc("started_at")
        .limit(1),
        "Pro",
    )
    .get()
)

await DB.table("incomes").where("amount", "<", DB.table("incomes").select_raw("AVG(amount)")).get()
```

### Full text where clauses

`where_full_text` uses the engine's own index — `MATCH … AGAINST` on
MySQL/MariaDB, `to_tsvector`/`to_tsquery` on PostgreSQL. An engine without one
says so rather than quietly matching something else:

```python
await DB.table("posts").where_full_text(["title", "body"], "rain shadow").get()
await DB.table("posts").where_full_text("body", "+rain -snow", mode="boolean").get()
await DB.table("posts").where_full_text("body", "rain", mode="websearch", language="english").get()
```

### Vector similarity

For pgvector and MariaDB's vector columns:

```python
await DB.table("documents").where_vector_similar_to("embedding", query_vector, min_similarity=0.75).get()
await DB.table("documents").select_vector_distance("embedding", query_vector, alias="distance").get()
await DB.table("documents").order_by_vector_distance("embedding", query_vector).limit(10).get()
```

## Ordering, grouping, limit and offset

```python
DB.table("users").order_by("name", "desc")
DB.table("users").order_by_desc("created_at")
DB.table("users").latest()          # newest by created_at
DB.table("users").oldest()
DB.table("users").in_random_order()
DB.table("users").reorder()          # drop every ordering
DB.table("users").reorder_desc("email")
DB.table("users").order_by_sub(latest_post_at, "desc")

DB.table("users").group_by("account_id").having("account_id", ">", 100)
DB.table("orders").group_by("department").having_between("total", [1_000, 5_000])

DB.table("users").skip(10).take(5)
DB.table("users").offset(10).limit(5)
DB.table("users").for_page(2, 15)
```

`having` may name an aggregate the query selected, and the aggregate is written
into the clause — PostgreSQL will not read an alias there.

## Conditional clauses

```python
DB.table("users").when(role, lambda query: query.where("role_id", role))
DB.table("users").when(sort, lambda query: query.order_by("votes", sort), lambda query: query.order_by("name"))
DB.table("users").unless(admin, lambda query: query.where("public", True))
```

## Insert statements

```python
await DB.table("users").insert({"email": "ada@example.com", "votes": 0})
await DB.table("users").insert([
    {"email": "ada@example.com", "votes": 0},
    {"email": "grace@example.com", "votes": 0},
])

await DB.table("users").insert_or_ignore({"id": 1, "email": "ada@example.com"})
await DB.table("users").insert_using(["email"], DB.table("guests").select("email"))

new_id = await DB.table("users").insert_get_id({"email": "ada@example.com"})
```

`insert_or_ignore` lets rows that would collide fall on the floor; it needs an
engine that knows about conflicts (SQLite, MySQL, PostgreSQL).

### Upserts

```python
await DB.table("flights").upsert(
    [
        {"departure": "Oakland", "destination": "San Diego", "price": 99},
        {"departure": "Chicago", "destination": "New York", "price": 150},
    ],
    unique_by=["departure", "destination"],
    update=["price"],
)
```

| Engine | Construct |
| --- | --- |
| SQLite / PostgreSQL | `INSERT … ON CONFLICT (unique_by) DO UPDATE` |
| MySQL | `INSERT … ON DUPLICATE KEY UPDATE` |
| Other | Probe, then write |

The columns in `unique_by` need a unique index or constraint.

## Update statements

```python
await DB.table("users").where("id", 1).update({"votes": 1})
await DB.table("users").update_or_insert({"email": "ada@example.com"}, {"votes": 2})
```

### Updating JSON columns

The arrow syntax works for writes too, and the surrounding document is left
alone:

```python
await DB.table("users").where("id", 1).update({"options->enabled": True})
```

### Increment and decrement

```python
await DB.table("users").increment("votes")
await DB.table("users").increment("votes", 5)
await DB.table("users").decrement("votes", 5, name="Ada")
await DB.table("users").increment_each({"votes": 5, "balance": 100})
```

## Delete statements

```python
await DB.table("users").delete()
await DB.table("users").where("votes", ">", 100).delete()
await DB.table("users").delete(1)     # by primary key
await DB.table("users").truncate()    # every row, and the counter back to one
```

## Pessimistic locking

Locks hold the selected rows for the rest of the transaction, so they belong
inside one:

```python
async with DB.transaction():
    await DB.table("users").where("votes", ">", 100).shared_lock().get()

async with DB.transaction():
    await DB.table("users").where("votes", ">", 100).lock_for_update().get()
```

`lock(False)` takes the intent back, and `lock("share")` names a mode directly.
An engine without row locks — SQLite — ignores the clause.

## Reusable query components

`tap` runs a callable against the builder and hands the builder back, so a
piece of a query can live in a function and be used from anywhere:

```python
def popular(query):
    query.where("votes", ">", 100).order_by_desc("votes")

await DB.table("flights").tap(popular).where("destination", "Paris").get()
```

`pipe` hands the builder to a callable and gives back whatever the callable
returns, which is how a component can end a chain:

```python
paginator = await DB.table("flights").pipe(lambda query: query.paginate(15))
```

`with_attributes` narrows a query and seeds the same values on anything it
creates, so a scoped query cannot make a row it would not find:

```python
posts = Post.query().with_attributes({"hidden": True})
await posts.first_or_create({"title": "Draft"})   # hidden=True, without saying so twice
```

## Debugging

```python
DB.table("users").where("votes", ">", 100).dump()          # SQL and bindings, keep going
DB.table("users").where("votes", ">", 100).dump_raw_sql()  # values written in
DB.table("users").where("votes", ">", 100).dd()            # print and stop
DB.table("users").where("votes", ">", 100).dd_raw_sql()

DB.table("users").where("votes", ">", 100).to_sql()        # placeholders
DB.table("users").where("votes", ">", 100).to_raw_sql()    # values written in
DB.table("users").where("votes", ">", 100).get_bindings()
```

`to_sql` leaves the placeholders where they are, because that is what the
driver will see; `to_raw_sql` writes the values in for reading.
