---
title: Migrations
description: Version-control your database schema with Almasix migrations.
---

Migrations are like version control for your database, allowing your team to define and share the application's database schema. Almasix's migration system is driven by timestamped Python files and a `migrations` table — not Alembic revision graphs.

## Generating migrations

```bash
smith make:migration create_flights_table
smith make:migration add_slug_to_posts_table
smith make:model Post -m          # model + create_posts_table migration
```

### Name inference

When you omit `--create` / `--table`, Almasix infers the stub from the migration name:

| Name | Stub | Table |
| --- | --- | --- |
| `create_users_table` / `create_users` | create | `users` |
| `add_description_column_to_posts_table` | update | `posts` |
| `drop_slug_from_posts_table` | update | `posts` |
| `rename_title_in_posts_table` | update | `posts` |
| `do_something_custom` | blank | — |

Prefer alter names **without** a leading `create_`: `add_slug_to_posts_table`. You may still pass `--create widgets` or `--table posts` to override inference.

## Migration structure

A create migration:

```python
# database/migrations/2026_01_01_000000_create_posts_table.py
from almasix.orm import Migration, Schema

class CreatePostsTable(Migration):
    async def up(self) -> None:
        await Schema.create(
            "posts",
            lambda table: (
                table.id(),
                table.string("title"),
                table.timestamps(),
            ),
        )

    async def down(self) -> None:
        await Schema.drop_if_exists("posts")
```

An update migration uses `Schema.table`:

```python
# database/migrations/2026_01_01_000001_add_slug_to_posts_table.py
class AddSlugToPostsTable(Migration):
    async def up(self) -> None:
        await Schema.table(
            "posts",
            lambda table: (table.string("slug").nullable().unique(),),
        )

    async def down(self) -> None:
        await Schema.table("posts", lambda table: table.drop_column("slug"))
```

Files must match `YYYY_MM_DD_HHMMSS_slug.py` and define a `Migration` subclass. The class name is the StudlyCase form of the slug (`create_posts_table` → `CreatePostsTable`).

## The schema builder

```python
# database/migrations/2026_01_01_000000_create_posts_table.py
await Schema.create(
    "posts",
    lambda table: (
        table.id(),
        table.string("title"),
        table.integer("user_id"),
        table.boolean("published").default(False),
        table.timestamps(),
        table.soft_deletes(),
    ),
)
await Schema.table("posts", lambda table: (table.string("slug").nullable(),))
await Schema.has_table("posts")
await Schema.has_column("posts", "slug")
await Schema.drop_if_exists("posts")
```

**Column helpers:** `id`, `big_increments`, `uuid`, `string`, `text`, `integer`, `big_integer`, `float`, `decimal`, `boolean`, `json`, `date`, `date_time`, `timestamp`, `timestamps`, `soft_deletes`, `foreign_id`, `morphs`.

**Modifiers:** `nullable()`, `default()`, `unique()`, `index()`, `primary()`, `after(col)` / `before(col)` (MySQL/MariaDB column position; ignored on SQLite/PostgreSQL).

**Indexes:** `unique("email")`, `unique(["a", "b"])`, `unique_index([...])`, `index([...])`.

**Alters:** `rename_column("from", "to")`, `drop_column(...)`, `foreign("user_id").references("id").on("users")`, `foreign_id("user_id").constrained()`, plus `cascade_on_delete()` / `null_on_delete()` / `cascade_on_update()` (and restrict / no_action variants).

```python
# database/migrations/2026_01_01_000001_add_slug_to_posts_table.py
await Schema.table(
    "posts",
    lambda table: (
        table.string("slug").nullable().after("title"),  # AFTER on MySQL
        table.rename_column("body", "content"),
        table.unique(["slug", "locale"]),
        table.foreign_id("user_id").constrained().cascade_on_delete(),
    ),
)
```

:::note
SQLite cannot `ALTER TABLE … ADD CONSTRAINT` for an **existing** column. Add foreign keys with `foreign_id(...).constrained()` when creating the column, or use MySQL, MariaDB, PostgreSQL, SQL Server, or Oracle.
:::


## Running migrations

```bash
smith migrate
smith migrate --seed
smith migrate:rollback            # --step N
smith migrate:fresh --seed
smith migrate:status
```

Always implement `down()` so rollbacks can reverse `up()`. Run Smith commands from your application root so `app.*` imports resolve.
