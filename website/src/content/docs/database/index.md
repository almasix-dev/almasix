---
title: Database — Getting Started
description: Configure connections, run raw SQL, split reads from writes, listen to queries, and manage transactions with the DB facade.
---

## Introduction

Almost every application talks to a database. Almasix reaches every supported
engine through one configuration file and two resolve paths: the `DB` facade
and SQL [query builder](/database/queries/) for tables, and
[document stores](/database/documents/) for MongoDB (or the in-process memory
store). [Articulate](/articulate/) models sit on either — `Model` on a table,
[`Document`](/articulate/documents/) on a collection.

Every call is a coroutine — the database is I/O, and Almasix never blocks the
event loop on it.

## Configuration

Connections live in `config/database.py`. A new application is ready to use
SQLite; PostgreSQL, MySQL/MariaDB, SQL Server, Oracle, and document stores
(MongoDB / memory) are a config block away.

```python title="config/database.py"
from almasix.config import env

config = {
    "default": env("DB_CONNECTION", "sqlite"),
    "connections": {
        "sqlite": {
            "driver": "sqlite",
            "database": env("DB_DATABASE", "database/database.sqlite"),
        },
        "pgsql": {
            "driver": "pgsql",
            "host": env("DB_HOST", "127.0.0.1"),
            "port": env("DB_PORT", "5432"),
            "database": env("DB_DATABASE", "almasix"),
            "username": env("DB_USERNAME", "almasix"),
            "password": env("DB_PASSWORD", ""),
        },
        "mongodb": {
            "driver": "mongodb",
            "dsn": env("MONGODB_DSN", ""),
            "database": env("MONGODB_DATABASE", "almasix"),
        },
        "documents": {
            "driver": "memory",
        },
    },
}
```

```bash title="terminal"
DB_CONNECTION=sqlite
DB_DATABASE=database/database.sqlite
```

SQLite `:memory:` databases share a static pool, so every acquire sees the same
in-memory database. Document connections use `store()` instead of
`connection()` — see [Document stores](/database/documents/).

### Installing a driver

SQLite ships with Almasix. The others are extras. For what each engine can
actually do — and which ones CI executes — see [Engine support](/database/engines/).

```bash title="terminal"
pip install almasix[pgsql]    # PostgreSQL (asyncpg)
pip install almasix[mysql]    # MySQL / MariaDB (aiomysql)
pip install almasix[sqlsrv]   # SQL Server (aioodbc + ODBC driver)
pip install almasix[oracle]   # Oracle
pip install almasix[db]       # all SQL drivers
pip install almasix[mongodb]  # MongoDB document store (Motor)
```

| `driver` | Async URL / store | Extra |
| --- | --- | --- |
| `sqlite` | `sqlite+aiosqlite:///…` | included |
| `pgsql` / `postgres` / `postgresql` | `postgresql+asyncpg://…` | `almasix[pgsql]` |
| `mysql` / `mariadb` | `mysql+aiomysql://…` | `almasix[mysql]` |
| `sqlsrv` / `mssql` / `sqlserver` | `mssql+aioodbc://…` | `almasix[sqlsrv]` |
| `oracle` | `oracle+oracledb_async://…?service_name=` | `almasix[oracle]` |
| `mongodb` | Motor client (collections) | `almasix[mongodb]` |
| `memory` | In-process document store | included |

A `url` key is used as given, with a sync prefix upgraded to its async driver.
SQL Server takes `odbc_driver` (default `ODBC Driver 18 for SQL Server`) and
`trust_server_certificate`; Oracle prefers `service_name` over `sid`.

### Read and write connections

A `read` and a `write` block point one connection at two hosts. Both inherit
everything the connection already says, so a block only names what differs:

```python title="config/database.py"
"mysql": {
    "driver": "mysql",
    "host": "primary.example.com",
    "database": "shop",
    "username": "shop",
    "password": env("DB_PASSWORD", ""),
    "read": {"host": "replica.example.com"},
    "write": {"host": "primary.example.com"},
    "sticky": True,
},
```

Selects go to the read host and everything else to the write host. With
`sticky` on, a context that has written keeps reading from the write host for
the rest of its life, so it sees its own rows rather than whatever the replica
has caught up to.

### Pooled connections

A connection through a transaction pooler cannot hold the session state that
migrations and schema inspection need. Give it a `direct` block and Almasix
routes that work around the pooler:

```python title="config/database.py"
"pgsql": {
    "driver": "pgsql",
    "host": "pooler.example.com",
    "port": 6543,
    "database": "app",
    "pooled": True,
    "direct": {"host": "db.example.com", "port": 5432},
},
```

Schema operations, the introspection commands, and `db` use the direct twin
without being asked; ordinary queries keep going through the pooler.

## Running SQL queries

```python title="app/http/controllers/user_controller.py"
from almasix.orm import DB

users = await DB.select("SELECT * FROM users WHERE active = :active", {"active": True})
user = await DB.select_one("SELECT * FROM users WHERE id = :id", {"id": 1})
count = await DB.scalar("SELECT count(*) FROM users")

await DB.insert("INSERT INTO users (email) VALUES (:email)", {"email": "ada@example.com"})
changed = await DB.update("UPDATE users SET votes = 100 WHERE name = :name", {"name": "Ada"})
removed = await DB.delete("DELETE FROM users")
await DB.statement("DROP TABLE users")
await DB.unprepared("ALTER TABLE users AUTO_INCREMENT = 1")
```

`select` and `select_one` return dictionaries, `scalar` the one value a query
returns, `update` and `delete` the number of rows they touched. `unprepared`
sends SQL exactly as written, for statements drivers refuse to prepare.

### Using multiple connections

```python title="app/http/controllers/user_controller.py"
await DB.connection("pgsql").select("SELECT 1")
await DB.table("users", connection="pgsql").get()
```

Pin a model to a connection with `Model.connection = "pgsql"`. Connections can
also be registered at runtime with `get_manager().add_connection(name, config)`
and closed with `DB.disconnect()` or `DB.disconnect(name)`.

### Listening for query events

`DB.listen` hears every statement the application runs — useful for a query log
or profiler:

```python title="app/providers/app_service_provider.py"
def log_query(query):
    logger.debug(query.sql, extra={"bindings": query.bindings, "ms": query.time})

DB.listen(log_query)
```

Each event carries `sql`, `bindings`, `time` in milliseconds, and
`connection_name`; `to_raw_sql()` writes the bindings in when you want to read
the query rather than run it.

### Monitoring cumulative query time

A page is rarely ruined by one slow query — it is ruined by two hundred quick
ones. `when_querying_for_longer_than` watches the total instead:

```python title="app/providers/app_service_provider.py"
DB.when_querying_for_longer_than(
    500,
    lambda connection, query: report_slow_request(connection.name, query.sql),
)
```

The budget is per context — a request, a job, a command. Read it with
`DB.total_query_duration()` and reset it with
`DB.reset_total_query_duration()`.

### Pretending

`DB.pretend` runs a callable and collects the statements it would have run,
without running any of them:

```python title="app/console/commands/audit_posts.py"
queries = await DB.pretend(lambda: Post.query().where("draft", True).delete())

for query in queries:
    print(query.to_raw_sql())
```

## Database transactions

As a block, the transaction commits when the block ends and rolls back if
anything is raised:

```python title="app/http/controllers/user_controller.py"
async with DB.transaction():
    await User.create(email="ada@example.com", name="Ada")
    await DB.table("audits").insert({"event": "user.created"})
```

Nested blocks are SAVEPOINTs, so an inner failure undoes only the inner work.

### Handling deadlocks

Pass a callable and the transaction can be retried when the engine reports a
deadlock:

```python title="app/http/controllers/order_controller.py"
await DB.transaction(create_the_order, attempts=5)
```

The callable may take the connection handle, and anything it returns is what
`DB.transaction` gives back. Only deadlocks are retried; every other failure is
raised the first time.

### Manually using transactions

```python title="app/http/controllers/user_controller.py"
await DB.begin_transaction()
try:
    await DB.table("users").update({"votes": 1})
except Exception:
    await DB.rollback()
    raise
else:
    await DB.commit()
```

`DB.transaction_level()` says how deep the open transactions are stacked, and a
hand-opened transaction inside a block is a SAVEPOINT within it.

### Deferring work until the commit

Work that must not happen for a row that never existed goes through
`after_commit`:

```python title="app/http/controllers/order_controller.py"
async with DB.transaction():
    order = await Order.create(...)
    DB.after_commit(lambda: dispatch(SendReceipt(order.id)))
```

Outside a transaction there is nothing to wait for, so the callback runs now. A
rollback throws it away with everything else.

## Connecting to the database CLI

`db` opens the client the engine ships, with the connection filled in:

```bash title="terminal"
smith db                # the default connection
smith db pgsql          # a named one
smith db mysql --read   # the read half of a split connection
smith db pgsql --pooled # through the pooler rather than around it
```

Almasix does not reimplement a SQL shell; it looks for `sqlite3`, `mysql`,
`psql`, or `sqlcmd`, and says which one it looked for if it is not installed.

## Inspecting your databases

```bash title="terminal"
smith db:show                 # the connection, its tables, and their sizes
smith db:show --counts        # with a row count per table (a full scan each)
smith db:show --views --types
smith db:table users          # columns, indexes, and foreign keys
smith db:table                # asks which table
```

Both take `--database=` to name a connection and `--json` for output a script
can read.

## Monitoring your databases

```bash title="terminal"
smith db:monitor
smith db:monitor --databases=pgsql,mysql --max=100
```

`db:monitor` reports how many sessions each connection has open, and fails when
one is over `--max` — enough for a scheduled check to notice a leak.

## Document stores

SQL is not the only kind of connection. Drivers `mongodb` and `memory` hold
collections; they resolve through `store()` and power
[`Document` models](/articulate/documents/). The full database-side story —
config, `store()` vs `connection()`, and when to choose collections — lives on
[Document stores (NoSQL)](/database/documents/).

## Next steps

Reach for the [query builder](/database/queries/) for most SQL reads and
writes, [document stores](/database/documents/) for MongoDB and the memory
store, and [Articulate](/articulate/) when you want Active Record persistence.
`DB.raw("price * 1.1")` and `await DB.connection().execute(...)` are the SQL
escape hatches when neither will say it.
