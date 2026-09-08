---
title: Database — Getting Started
description: Configure database connections and run queries with the DB facade.
---

Almost every modern web application interacts with a database. Almasix makes this interaction simple through a unified API across supported drivers, a fluent query builder, and **Articulate** — Almasix's Active Record ORM.

## Configuration

Configure connections in the snippet below. A newly created application is ready to use SQLite; you may also configure PostgreSQL, MySQL / MariaDB, SQL Server, and optionally Oracle.

```python
# config/database.py
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
    },
}
```

Set the active connection in `.env`:

```bash
DB_CONNECTION=sqlite
DB_DATABASE=database/database.sqlite
```

SQLite `:memory:` databases are supported; Almasix uses a static pool so every acquire shares the same in-memory database.

## Installing a driver

SQLite ships with Almasix. Install extras for other engines:

```bash
pip install almasix[pgsql]    # PostgreSQL (asyncpg)
pip install almasix[mysql]    # MySQL / MariaDB (aiomysql)
pip install almasix[sqlsrv]   # SQL Server (aioodbc + ODBC driver)
pip install almasix[oracle]   # Oracle (optional community niche)
pip install almasix[db]       # all optional drivers
```

| `driver` | Async URL | Extra |
| --- | --- | --- |
| `sqlite` | `sqlite+aiosqlite:///…` | included |
| `pgsql` / `postgres` / `postgresql` | `postgresql+asyncpg://…` | `almasix[pgsql]` |
| `mysql` / `mariadb` | `mysql+aiomysql://…` | `almasix[mysql]` |
| `sqlsrv` / `mssql` / `sqlserver` | `mssql+aioodbc://…` | `almasix[sqlsrv]` |
| `oracle` | `oracle+oracledb_async://…?service_name=` | `almasix[oracle]` |

A `url` key on a connection dict is used as-is (sync prefixes are upgraded to async drivers). For SQL Server, set `odbc_driver` (default `ODBC Driver 18 for SQL Server`) and `trust_server_certificate` as needed. For Oracle, prefer `service_name` (or `sid`).

:::note[Oracle]
Oracle is an optional Almasix extra for teams that need it — not part of the default SQLite / PostgreSQL / MySQL / SQL Server set.
:::


## Running raw queries

The `DB` facade gives you a simple way to run queries:

```python
# app/http/controllers/example_controller.py
from almasix.orm import DB

users = await DB.select(
    "SELECT * FROM users WHERE email = :email",
    {"email": email},
)
row = await DB.select_one("SELECT 1 AS n")
await DB.statement("DELETE FROM sessions WHERE id = :id", {"id": sid})
```

You may also start a query builder against a table (results are dictionaries, not models):

```python
# app/http/controllers/example_controller.py
await DB.table("users").where("email", email).get()
```

## Transactions

```python
# app/http/controllers/example_controller.py
async with DB.transaction():
    await User.create(email="a@b.c", name="Ada")
    async with DB.transaction():
        # Nested transactions use SAVEPOINTs
        await User.create(email="b@b.c", name="Grace")
```

## Using multiple connections

```python
# app/http/controllers/example_controller.py
await DB.connection("pgsql").table("users").get()
```

Pin a Articulate model to a connection with `Model.connection = "pgsql"`. You may also register connections at runtime with `DatabaseManager.add_connection(name, config)` and dispose them with `disconnect()` / `disconnect(name)`.

## Next steps

Prefer the fluent [query builder](/database/queries/) for most reads and writes, and [Articulate models](/articulate/) when you want Active Record persistence and relationships.

Escape hatches (use sparingly): `DB.raw("price * 1.1")` and `await DB.connection().execute(...)`.
