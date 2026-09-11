---
title: Document stores (NoSQL)
description: Configure MongoDB and the in-memory document store beside SQL connections — store() vs connection(), and when to use collections.
---

## Introduction

Almasix treats document stores as first-class database connections. A
connection whose driver is `mongodb` or `memory` holds **collections** rather
than tables. You configure them in the same `config/database.py` file as SQLite
and PostgreSQL; the framework refuses to confuse the two kinds.

| Concern | SQL | Documents |
| --- | --- | --- |
| Config | `connections` block, `driver: sqlite` / `pgsql` / … | Same file, `driver: mongodb` or `memory` |
| Resolve | `DB.connection()` / `get_manager().connection()` | `get_manager().store()` |
| Models | `Model` on a table | [`Document`](/articulate/documents/) on a collection |
| Schema | Migrations + Blueprint | Indexes on the model — no SQL migrations |
| Joins | Query builder | Raise `UnsupportedQueryError` — use refs, embeds, or pipelines |

This page is the database story; the [Articulate Documents](/articulate/documents/)
section is the model story.

## Configuration

```python title="config/database.py"
from almasix.config import env

config = {
    "default": env("DB_CONNECTION", "sqlite"),
    "connections": {
        "sqlite": {
            "driver": "sqlite",
            "database": env("DB_DATABASE", "database/database.sqlite"),
        },
        "mongodb": {
            "driver": "mongodb",
            "dsn": env("MONGODB_DSN", ""),
            "host": env("MONGODB_HOST", "127.0.0.1"),
            "port": env("MONGODB_PORT", 27017),
            "database": env("MONGODB_DATABASE", "almasix"),
            "username": env("MONGODB_USERNAME", ""),
            "password": env("MONGODB_PASSWORD", ""),
            # "options": {},  # passed to Motor, e.g. TLS
        },
        "documents": {
            "driver": "memory",
        },
    },
}
```

```bash title="terminal"
pip install "almasix[mongodb]"   # Motor — required for the mongodb driver
```

| `driver` | Extra | Role |
| --- | --- | --- |
| `mongodb` | `almasix[mongodb]` | Production document store |
| `memory` | included | In-process collections — tests, demos, no server |

A `dsn` (or `url`) wins over host/port. Atlas and replica-set URIs go in
`MONGODB_DSN`. The scaffold ships both blocks so switching a model's
`connection` does not require reshaping config.

## Resolving a store

```python title="app/console/commands/inspect_stores.py"
from almasix.orm import get_manager

manager = get_manager()

manager.store("mongodb")             # DocumentStore
manager.connection("sqlite")         # SQL Connection
manager.is_document("mongodb")       # True
manager.is_document("sqlite")        # False
manager.document_connection_names()  # ["documents", "mongodb", ...]

# manager.connection("mongodb")      # ConnectionError_ — use store()
# manager.store("sqlite")            # ConnectionError_ — use connection()
```

`DB.select` / `DB.table` / transactions stay on SQL connections. Document work
goes through [`Document` models](/articulate/documents/getting-started/) (or the
store's own methods when you need an escape hatch).

## When to use which

| Prefer documents when… | Prefer SQL when… |
| --- | --- |
| Data is naturally nested or schema-flexible | You need joins, FKs, or transactional DDL |
| You want MongoDB's write / query shape | Reports and relational integrity matter most |
| Tests should run without a server (`memory`) | The rest of the app is already SQL Articulate |

Mixing both in one app is normal: a document can reference a SQL user, and a
SQL model can store a document key. See
[Relationships & embeds](/articulate/documents/relationships/).

## What lives where in the docs

| Topic | Page |
| --- | --- |
| This overview + config | **You are here** |
| SQL engines matrix | [Engine support](/database/engines/) |
| First `Document`, keys, generators | [Documents: Getting Started](/articulate/documents/getting-started/) |
| Query builder on collections | [Documents: Querying](/articulate/documents/querying/) |
| Embeds and cross-store refs | [Documents: Relationships](/articulate/documents/relationships/) |
| Indexes and `documents:index` | [Documents: Indexes](/articulate/documents/indexes/) |
| Pipelines | [Documents: Aggregations](/articulate/documents/aggregations/) |

## Try it in your app

Add a `memory` (or `mongodb`) connection in `config/database.py`, define a
`Document` subclass, then create and query a few rows from a Smith command or a
test. Point the documents connection at `mongodb` and set `MONGODB_DSN` when
you want a real server — the same model code works on both stores. See
[Articulate Documents](/articulate/documents/) for the model API.
