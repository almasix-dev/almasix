---
title: Engine support
description: Which databases Almasix claims, what each feature needs, and what SQLite cannot do.
---

## Introduction

Almasix talks to every supported engine through one API. That does not mean
every feature means the same thing on every engine. This page is the honest
matrix: what runs in CI, what compiles for best-effort engines, and where
SQLite (or another engine) refuses rather than pretends.

## Engines Almasix claims

### SQL

| Engine | Driver extra | Executed in CI | Notes |
| --- | --- | --- | --- |
| SQLite | included (`aiosqlite`) | yes | Default for new apps and the offline suite |
| PostgreSQL | `almasix[pgsql]` (`asyncpg`) | yes | Preferred server engine for transactional DDL |
| MySQL | `almasix[mysql]` (`aiomysql`) | yes | Same driver path as MariaDB |
| MariaDB | `almasix[mariadb]` (`aiomysql`) | yes (same suite as MySQL) | Use the `mariadb` driver label when you care |
| SQL Server | `almasix[sqlsrv]` (`aioodbc`) | compile-only | URL construction and DDL compilation; no CI service yet |
| Oracle | `almasix[oracle]` (`oracledb`) | compile-only | Best-effort; same status as SQL Server |

`pip install almasix[db]` pulls every SQL driver.

### Document stores

| Store | Driver extra | Executed in CI | Notes |
| --- | --- | --- | --- |
| Memory | included | yes (unit + smoke) | In-process collections — the document `:memory:` |
| MongoDB | `almasix[mongodb]` (`motor`) | unit fakes + optional live | Production document store; see [Document stores](/database/documents/) |

Document connections share `config/database.py` with SQL but resolve through
`store()`, not `connection()`. The model layer is
[Articulate Documents](/articulate/documents/); the database overview is
[Document stores (NoSQL)](/database/documents/).

## Feature matrix

| Feature | SQLite | PostgreSQL | MySQL / MariaDB | SQL Server | Oracle |
| --- | --- | --- | --- | --- | --- |
| Query builder + Articulate | yes | yes | yes | compile / best-effort | compile / best-effort |
| Native upsert | `ON CONFLICT` | `ON CONFLICT` | `ON DUPLICATE KEY` | probe fallback | probe fallback |
| JSON path wheres / updates | yes (3.39+) | yes (`json` / `jsonb`) | yes (8+) | limited | no |
| Full-text search | no | `to_tsvector` | `MATCH … AGAINST` | no | no |
| Row locks (`lock_for_update`) | ignored | yes | yes | yes | yes |
| Transactions + savepoints | yes | yes | yes | yes | yes |
| Transactional DDL | no (driver) | yes | no (autocommit DDL) | yes | varies |
| `change()` / drop foreign key | raises | yes | yes | yes | yes |
| Column modifiers (`after`, `comment`, …) | ignored / N/A | partial | full | partial | partial |

When an engine cannot do the work, Almasix raises (or documents the skip) —
it does not emit SQL that quietly means something else. See
[Migrations](/database/migrations/) for schema limits and
[Query Builder](/database/queries/) for JSON, upsert, and locking details.

## What SQLite cannot do

SQLite is excellent for development and tests. It is not a stand-in for every
server feature:

- **`change()`** — cannot alter a column in place; Almasix raises instead of
  rebuilding the table behind your back.
- **Foreign-key surgery** — cannot `ADD CONSTRAINT` for an existing column,
  drop a foreign key, drop a primary key, or rename an index the way MySQL and
  PostgreSQL can.
- **Row locks** — `lock_for_update` / `shared_lock` are accepted and ignored.
- **Transactional DDL** — `CREATE TABLE` often lands outside the transaction
  your migration opened.
- **Full-text / vectors** — no `MATCH … AGAINST`, no `to_tsvector`, no pgvector.

Use PostgreSQL or MySQL in CI (or locally) when you rely on those paths. The
dialect conformance suite (`tests/test_m44_conformance.py`) runs schema DDL,
upserts, JSON wheres, locking, transactions, and pagination against SQLite,
PostgreSQL, and MySQL in GitHub Actions.

## Running the suite against another engine

```bash
pip install -e ".[dev,pgsql,mysql]"

# SQLite (default) — offline
pytest -q tests/test_m44_conformance.py

# PostgreSQL
ALMASIX_TEST_DB=pgsql DB_HOST=127.0.0.1 DB_PORT=5432 \
  DB_DATABASE=almasix_test DB_USERNAME=almasix DB_PASSWORD=secret \
  pytest -q tests/test_m44_conformance.py

# MySQL
ALMASIX_TEST_DB=mysql DB_HOST=127.0.0.1 DB_PORT=3306 \
  DB_DATABASE=almasix_test DB_USERNAME=almasix DB_PASSWORD=secret \
  pytest -q tests/test_m44_conformance.py
```

`make test-orm-engines` is the same target with whatever `ALMASIX_TEST_DB` the
environment already holds. The living example `smith progress:engines` probes
the app's default connection the same way.
