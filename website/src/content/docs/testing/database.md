---
title: Database Testing
description: A fresh database for every test, transactions that take their writes back, and assertions about the rows a request left behind.
---

## Introduction

A test that writes to the database has to decide what happens to those rows
when it finishes. Almasix offers the two answers Laravel does: migrate a fresh
database before each test, or run each test inside a transaction and roll it
back.

```python
class PostTest(TestCase):
    use_refresh_database = True

    async def test_a_post_is_written(self) -> None:
        await self.post("/posts", {"title": "Hello"})

        await self.assert_database_has("posts", {"title": "Hello"})
```

## Resetting between tests

| Setting | What it does |
| --- | --- |
| `use_refresh_database` | Drops every table and runs the migrations again, before each test |
| `use_database_transactions` | Wraps each test in a transaction, and rolls it back afterwards |

Transactions are much the faster of the two, and enough for a suite whose
schema does not change. `use_refresh_database` starts from the migrations on
disk, which is what you want when a test cares about the schema itself.

Both are available as functions, for a test that is not a `TestCase`:

```python
from almasix.testing import database_transactions, refresh_database

await refresh_database(path=Path("database/migrations"))

async with database_transactions():
    await Post.create({"title": "Temporary"})
    # ... nothing written here survives the block
```

`refresh_database()` reads `database/migrations` relative to the application,
and returns the migrations it ran.

## Row assertions

```python
await assert_database_has("posts", {"title": "Hello"})
await assert_database_has(Post, {"title": "Hello"})   # a model names its table
await assert_database_missing("posts", {"title": "Draft"})
await assert_database_count("posts", 3)
await assert_database_empty("posts")
```

A failing assertion prints the first few rows the table actually holds, so the
message says what went wrong rather than only that something did.

## Model assertions

```python
await assert_model_exists(post)
await assert_model_missing(post)
await assert_soft_deleted(post)
await assert_soft_deleted(post, {"title": "Hello"})
await assert_not_soft_deleted(post)
```

These read the model's own table, key, and connection, so a model on a second
connection is checked on that connection. `assert_soft_deleted` takes a
`column=` for a model that names its trashed column something other than
`deleted_at`.

Inside a `TestCase`, each of these is a method — `await self.assert_database_has(...)`.

## Seeding

A test that needs rows should usually make them itself, with a factory:

```python
class PostTest(TestCase):
    use_refresh_database = True

    async def test_the_index_paginates(self) -> None:
        await Post.factory().count(30).create()

        response = await self.get("/posts")

        response.assert_ok().assert_see("Page 1")
```

See [Factories](/database/factories/) for states, sequences, and relationships,
and [Seeding](/database/seeding/) for `smith db:seed`.

## Which database

Nothing here chooses a database for you: the connection is the one
`config/database.py` returns, and `smith test` sets `APP_ENV=testing` so that
file can choose a different one for a test run.

```python
# config/database.py
"default": env("DB_CONNECTION", "sqlite" if env("APP_ENV") == "testing" else "postgres"),
```

An in-memory SQLite database is the fastest thing a suite can run against, and
`refresh_database` makes it a fresh one every test.
