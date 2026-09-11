---
title: Migrations
description: Version-control your database schema with Almasix migrations.
---

Migrations are version control for your database. Each one is a timestamped
Python file describing a change, and a `migrations` table records which have
run, so a checkout of your project can bring any database up to the schema the
code expects.

Almasix compiles schema changes through SQLAlchemy, so one blueprint means the
same thing on SQLite, MySQL, MariaDB, PostgreSQL, SQL Server and Oracle — in
each engine's own words. There are no revision graphs: migrations run in
filename order.

## Generating migrations

```bash title="terminal"
smith make:migration create_flights_table
smith make:migration add_slug_to_posts_table
smith make:model Post -m          # model + create_posts_table migration
```

### Name inference

When you omit `--create` / `--table`, Almasix infers the stub from the migration
name:

| Name | Stub | Table |
| --- | --- | --- |
| `create_users_table` / `create_users` | create | `users` |
| `add_description_column_to_posts_table` | update | `posts` |
| `drop_slug_from_posts_table` | update | `posts` |
| `rename_title_in_posts_table` | update | `posts` |
| `do_something_custom` | blank | — |

Prefer alter names **without** a leading `create_`: `add_slug_to_posts_table`.
You may still pass `--create widgets` or `--table posts` to override inference.

### Squashing migrations

As an application grows, its migrations directory fills with files that only
ever run in order on a fresh database. `schema:dump` writes the current schema
— and the migration history behind it — to one file:

```bash title="terminal"
smith schema:dump
smith schema:dump --prune         # and delete the files it stands in for
smith schema:dump --database=pgsql
```

The dump lands in `database/schema/{connection}-schema.sql`. A database that
has never run a migration can load it instead of replaying everything:

```bash title="terminal"
smith migrate --schema-path=database/schema/sqlite-schema.sql
```

Almasix reads the schema back through the inspector, so a dump is the same
shape on every engine and needs no client binary installed.

## Migration structure

A create migration:

```python title="database/migrations/2026_01_01_000000_create_posts_table.py"
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

```python title="database/migrations/2026_01_01_000001_add_slug_to_posts_table.py"
from almasix.orm import Migration, Schema

class AddSlugToPostsTable(Migration):
    async def up(self) -> None:
        await Schema.table(
            "posts",
            lambda table: (table.string("slug").nullable().unique(),),
        )

    async def down(self) -> None:
        await Schema.table("posts", lambda table: table.drop_column("slug"))
```

Files must match `YYYY_MM_DD_HHMMSS_slug.py` and define a `Migration` subclass.
The class name is the StudlyCase form of the slug (`create_posts_table` →
`CreatePostsTable`).

### Setting the connection

A migration that belongs to another database says so:

```python title="database/migrations/2026_01_01_000002_create_audit_table.py"
class CreateAuditTable(Migration):
    connection = "audit"

    async def up(self) -> None: ...
```

### Skipping a migration

`should_run` decides whether the migration applies at all — a feature that only
exists on some deployments, say. A migration that declines is not recorded, so
it stays pending and is reconsidered next time.

```python title="database/migrations/2026_01_01_000003_create_search_index_table.py"
class CreateSearchIndexTable(Migration):
    def should_run(self) -> bool:
        return config("scout.driver") == "database"
```

### Transactions

Where the engine can roll DDL back, each migration runs inside a transaction,
so a failure halfway leaves nothing behind. PostgreSQL and SQL Server can;
MySQL and MariaDB commit every schema statement as it runs, and SQLite's Python
driver runs `CREATE TABLE` outside the transactions it opens, so there only the
data a migration writes comes back.

Set `within_transaction = False` to run one unwrapped.

## Running migrations

```bash title="terminal"
smith migrate
smith migrate --seed
smith migrate --step              # one batch per migration
smith migrate --pretend           # print the SQL, run none of it
smith migrate --path=database/extra,database/more
smith migrate --database=pgsql
```

Because schema changes run through the connection like any other statement,
`--pretend` prints exactly what would be sent:

```text title="terminal"
Migrated: 2026_01_01_000000_create_posts_table
  CREATE TABLE posts (id BIGINT NOT NULL, title VARCHAR(255), PRIMARY KEY (id))
```

### Forcing migrations to run in production

`migrate`, `migrate:rollback` and `migrate:fresh` refuse to run against a
production database without `--force`. Outside production nothing is asked.
`migrate:reset` and `migrate:refresh` ask wherever they run, because they undo
work everywhere.

```bash title="terminal"
smith migrate --force
```

`--graceful` reports a failure as success, for a deploy pipeline that must not
stop when the database is not reachable yet.

### Rolling back

```bash title="terminal"
smith migrate:rollback            # the last batch
smith migrate:rollback --step=3   # the last three migrations
smith migrate:rollback --batch=2  # everything in batch 2
smith migrate:rollback --pretend
smith migrate:reset               # every migration, newest first
smith migrate:refresh --seed      # roll everything back and run it again
smith migrate:fresh --seed        # drop every table and start over
```

`--step` counts migrations. `migrate --step` is the other half of that: it
gives each migration its own batch, so each can be rolled back on its own
later.

`migrate:fresh` drops every table with foreign keys switched off, so a schema
whose tables point at each other has no wrong order to be dropped in.

### Migration status

```bash title="terminal"
smith migrate:status
smith migrate:status --pending
```

```text title="terminal"
Ran [1]    2026_01_01_000000_create_posts_table
Ran [2]    2026_01_02_000000_create_tags_table
Pending    2026_01_03_000000_add_slug_to_posts_table
```

## Tables

### Creating tables

```python title="database/migrations/2026_01_01_000000_create_users_table.py"
await Schema.create(
    "users",
    lambda table: (
        table.id(),
        table.string("name"),
        table.string("email").unique(),
        table.timestamps(),
    ),
)
await Schema.create_if_not_exists("users", ...)
```

Table options, for the engines that have them:

```python title="database/migrations/2026_01_01_000000_create_users_table.py"
def build(table):
    table.engine("InnoDB")
    table.charset("utf8mb4")
    table.collation("utf8mb4_unicode_ci")
    table.comment("Everyone who has signed up")
    table.id()
```

### Checking for existence

```python title="database/migrations/2026_01_01_000010_guard_columns.py"
await Schema.has_table("users")
await Schema.has_column("users", "email")
await Schema.has_columns("users", ["email", "name"])
await Schema.has_index("users", ["email"])
await Schema.has_index("users", "users_email_unique")
await Schema.column_type("users", "email")
```

### Updating tables

```python title="database/migrations/2026_01_01_000011_add_votes_to_users_table.py"
await Schema.table("users", lambda table: table.integer("votes").default(0))
```

Two conditional forms save an `if`:

```python title="database/migrations/2026_01_01_000012_adjust_votes.py"
await Schema.when_table_has_column("users", "votes", lambda table: table.drop_column("votes"))
await Schema.when_table_doesnt_have_column("users", "votes", lambda table: table.integer("votes"))
```

### Renaming and dropping

```python title="database/migrations/2026_01_01_000013_drop_posts_table.py"
await Schema.rename("posts", "articles")
await Schema.drop("posts")
await Schema.drop_if_exists("posts")
await Schema.drop_all_tables()
```

### Inspecting the schema

```python title="app/console/commands/inspect_schema.py"
await Schema.table_names()
await Schema.columns("users")        # name, type, nullable, default
await Schema.get_indexes("users")    # name, columns, unique, primary
await Schema.get_foreign_keys("users")
await Schema.get_views()
```

The `db:show`, `db:table` and `db:monitor` commands read the same reflection
from the command line.

## Columns

### Available column types

**Keys.** `id`, `increments`, `tiny_increments`, `small_increments`,
`medium_increments`, `big_increments`. `id()` is `big_increments()`; SQLite
narrows every width to `INTEGER`, because that is the only one it counts up.

**Strings and text.** `char`, `string`, `tiny_text`, `text`, `medium_text`,
`long_text`.

**Numbers.** `tiny_integer`, `small_integer`, `medium_integer`, `integer`,
`big_integer`, and an `unsigned_*` twin of each; `float`, `double`, `decimal`,
`unsigned_decimal`, `boolean`.

**Enumerations.** `enum(name, values)` — a check constraint everywhere but
MySQL, which has the type. `set(name, values)` — MySQL and MariaDB only;
elsewhere it is a string wide enough to hold the list.

**Documents.** `json`, `jsonb` (native on PostgreSQL, plain JSON elsewhere).

**Dates and times.** `date`, `date_time`, `date_time_tz`, `time`, `time_tz`,
`timestamp`, `timestamp_tz`, `timestamps`, `timestamps_tz`,
`nullable_timestamps`, `soft_deletes`, `soft_deletes_tz`, `year`.

**Identifiers.** `uuid` (native on PostgreSQL, `VARCHAR(36)` elsewhere),
`ulid`, `ip_address`, `mac_address`, `remember_token`, `binary`.

**Relationships.** `foreign_id`, `foreign_uuid`, `foreign_ulid`,
`foreign_id_for(Model)`, `morphs`, `nullable_morphs`, `uuid_morphs`,
`ulid_morphs`.

**Engine-specific.** `vector(name, dimensions)` for pgvector and MariaDB,
`geometry` and `geography` for spatial data, and `raw_column(name, definition)`
for a type Almasix has no name for.

```python title="database/migrations/2026_01_01_000020_create_places_table.py"
await Schema.create(
    "places",
    lambda table: (
        table.id(),
        table.string("name"),
        table.enum("kind", ["cafe", "bar"]),
        table.geography("location", "point"),
        table.vector("embedding", 1536),
        table.jsonb("meta"),
        table.timestamps_tz(),
    ),
)
```

### Column modifiers

| Modifier | What it does |
| --- | --- |
| `nullable()` | Allow `NULL` |
| `default(value)` | A default written into the DDL, so any writer gets it |
| `unsigned()` | No negatives (MySQL / MariaDB) |
| `unique()` / `index()` / `primary()` | Index the column |
| `comment(text)` | Describe the column (MySQL / MariaDB) |
| `charset()` / `collation()` | Character set and collation (MySQL / MariaDB) |
| `first()` / `after(col)` / `before(col)` | Where the column goes (MySQL / MariaDB) |
| `invisible()` | Hide from `SELECT *` (MySQL / MariaDB) |
| `use_current()` | Default to the moment the row is written |
| `use_current_on_update()` | Touch on every update (MySQL / MariaDB) |
| `virtual_as(expr)` / `stored_as(expr)` | A computed column |
| `generated_as()` / `always()` | An identity column |
| `auto_increment()` / `start_from(n)` | Count up, from a given number |

```python title="database/migrations/2026_01_01_000021_column_modifiers.py"
table.string("status").default("draft").comment("Editorial state")
table.timestamp("created_at").use_current()
table.string("full_name").stored_as("first_name || ' ' || last_name")
```

### Modifying columns

`change()` restates a column. Everything it says is applied and everything it
leaves out is dropped — engines that take a whole column definition enforce
this:

```python title="database/migrations/2026_01_01_000022_change_name_column.py"
await Schema.table(
    "users",
    lambda table: table.string("name", 50).nullable(False).default("Anonymous").change(),
)
```

:::note
SQLite cannot change a column in place. Add the new column, copy the values
across, and drop the old one — or run the migration on MySQL, MariaDB,
PostgreSQL or SQL Server.
:::

### Renaming and dropping columns

```python title="database/migrations/2026_01_01_000023_rename_body.py"
await Schema.table("users", lambda table: table.rename_column("body", "content"))
await Schema.table("users", lambda table: table.drop_column("votes", "avatar"))
```

Convenience drops for the helpers that added several columns at once:

```python title="database/migrations/2026_01_01_000024_drop_helpers.py"
table.drop_morphs("taggable")
table.drop_timestamps()
table.drop_soft_deletes()
table.drop_remember_token()
```

## Indexes

### Creating indexes

```python title="database/migrations/2026_01_01_000025_add_indexes.py"
table.string("email").unique()          # on the column
table.unique("email")                   # on the table
table.unique(["locale", "slug"])
table.index(["published_at", "title"])
table.primary(["locale", "slug"])
table.index("slug", "posts_slug_lookup")  # with a name of your own
```

Index names default to `ix_{table}_{columns}` and `uq_{table}_{columns}`.

### Renaming and dropping indexes

```python title="database/migrations/2026_01_01_000026_drop_indexes.py"
table.rename_index("ix_posts_slug", "posts_slug_lookup")
table.drop_index("ix_posts_slug")
table.drop_unique(["slug"])
table.drop_primary()
```

### Foreign key constraints

```python title="database/migrations/2026_01_01_000027_add_foreign_keys.py"
table.foreign_id("user_id").constrained()
table.foreign_id("author_id").constrained("users")
table.foreign("user_id").references("id").on("users")
```

The action a delete or an update takes:

```python title="database/migrations/2026_01_01_000028_cascade_keys.py"
table.foreign_id("user_id").constrained().cascade_on_delete()
```

`cascade_on_delete`, `restrict_on_delete`, `null_on_delete`,
`no_action_on_delete`, and the same four for updates. Dropping them:

```python title="database/migrations/2026_01_01_000029_drop_foreign_keys.py"
table.drop_foreign(["user_id"])
table.drop_constrained_foreign_id("user_id")   # the key, then the column
```

Constraint checking can be switched off around a block:

```python title="database/migrations/2026_01_01_000030_without_fks.py"
async with Schema.without_foreign_key_constraints():
    await Schema.drop("users")

await Schema.disable_foreign_key_constraints()
await Schema.enable_foreign_key_constraints()
```

:::note
SQLite cannot `ALTER TABLE … ADD CONSTRAINT` for an **existing** column, drop a
foreign key, drop a primary key, or rename an index. Add foreign keys with
`foreign_id(...).constrained()` when creating the column, or use MySQL,
MariaDB, PostgreSQL, SQL Server, or Oracle.
:::

## Events

The migrator announces what it is doing, so a deploy log or a dashboard can
follow along:

```python title="app/providers/app_service_provider.py"
from almasix.events import Event
from almasix.orm.migration import MigrationEnded, MigrationStarted, NoPendingMigrations

Event.listen(MigrationStarted, lambda event: logger.info("running %s", event.migration))
Event.listen(MigrationEnded, lambda event: logger.info("%s in %.0fms", event.migration, event.elapsed))
Event.listen(NoPendingMigrations, lambda event: logger.info("nothing to do"))
```

`MigrationStarted` and `MigrationEnded` both carry the migration name and its
`direction` (`up` or `down`); `MigrationEnded` adds `elapsed`, the milliseconds
it took, which is also what the command prints.

Always implement `down()` so rollbacks can reverse `up()`. Run Smith commands
from your application root so `app.*` imports resolve.
