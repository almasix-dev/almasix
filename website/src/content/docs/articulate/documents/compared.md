---
title: Documents — Compared with Laravel
description: How Almasix Articulate documents map to Laravel 13's MongoDB integration — shipped, partial, missing, and deliberate deviations.
---

Laravel 13 documents MongoDB on
[laravel.com/docs/13.x/mongodb](https://laravel.com/docs/13.x/mongodb) via the
official [`mongodb/laravel-mongodb`](https://github.com/mongodb/laravel-mongodb)
package. Almasix does not vendor that package; it implements Eloquent-on-collections
inside Articulate (`Document`, `DocumentBuilder`, embeds, indexes) and shares
the same mental model where the semantics match.

This page is the parity map after the stability-track audit. Features Laravel
lists that sit outside Articulate (cache, queue, GridFS, Scout) are named as
**missing** — not as silent half-implementations.

## Eloquent-on-collections

| Feature | Almasix | Notes |
| --- | --- | --- |
| Document / Eloquent models on collections | **Shipped** | `Document` extends `Model` |
| Config connection (`dsn` + database) | **Shipped** | Plus host/port/user/pass and `options` |
| `almasix[mongodb]` / Motor | **Shipped** | Never appears in app signatures |
| Query builder (where, order, limit, CRUD, upsert, inc) | **Shipped** | `DocumentBuilder` |
| Embedded relationships | **Shipped** | `embeds_one` / `embeds_many` |
| Reference relationships | **Shipped** | Including cross-store to SQL |
| Soft deletes, factories, casts, events | **Shipped** | Inherited from Articulate |
| UUID / ULID keys | **Shipped** | Via `HasUuids` / `HasUlids` |
| Indexes from the model | **Shipped** | `indexes` + `documents:index` |
| Raw aggregation pipelines | **Partial** | `raw_aggregate`; no fluent Aggregation Builder |
| Text / `$text` helpers | **Partial** | Use `where_raw` / pipelines |
| `vectorSearch` / Atlas Search | **Missing** | SQL builder has vector helpers; documents do not |
| Many-to-many without pivots | **N/A** | Prefer id arrays or edge collections — no fake pivots |
| Schema Blueprint for collections | **N/A** | Indexes on the model instead |
| Cursor pagination on documents | **Missing** | Offset + simple pagination ship |
| Transactions on Mongo | **Missing** | Needs a replica set; `DB.transaction()` is SQL-only |
| In-memory document store | **Shipped** | First-class `memory` driver (Laravel has no equivalent) |

## Laravel feature list (package integrations)

Laravel's MongoDB page also advertises drivers that plug into other framework
surfaces. Almasix does **not** claim these yet:

| Laravel feature | Almasix status |
| --- | --- |
| MongoDB cache driver (TTL indexes) | **Missing** — cache drivers are separate |
| MongoDB queue driver | **Missing** |
| GridFS filesystem adapter | **Missing** — filesystem disks are separate |
| MongoDB Scout engine | **Missing** — Scout has `database` / `collection` / Meilisearch |
| Third-party packages “just work” on Mongo | **Partial** — Articulate packages that use `Model` may; SQL-only packages will not |

Those belong in later releases if product demand warrants them — not as
footnotes pretending to ship with `Document`.

## Deliberate deviations

- **Transactions.** Mongo multi-document transactions need a replica set.
  Almasix will not pretend a standalone node has them. Use SQL transactions,
  or redesign for single-document atomicity.
- **Keys.** Almasix does not wrap keys in a framework `ObjectId` type.
  Memory keys are hex strings; Mongo returns Motor's values. Prefer
  `get_key()` / `find` over assuming a Python `str` always.
- **Embeds save through the parent.** An embedded document has no collection;
  `save()` writes the parent field.
- **`memory` is a real store.** The same code path runs in CI and on a laptop
  with no Mongo — the document answer to SQLite `:memory:`.
- **Joins raise.** `UnsupportedQueryError` beats a silent wrong answer.

## Where to go next

- [Getting started](/articulate/documents/getting-started/) — install and config
- [Querying](/articulate/documents/querying/) — builder and refusals
- [Aggregations](/articulate/documents/aggregations/) — pipelines
- Laravel's own guide: [MongoDB · Laravel 13.x](https://laravel.com/docs/13.x/mongodb)
