---
title: Document store feature map
description: What Articulate Documents ship today — core ORM features, gaps, and deliberate limits versus common document-ORM expectations.
---

Articulate Documents put Active Record models on **collections** (MongoDB or the
in-process `memory` store) instead of SQL tables. This page is a candid map of
what works, what is only partly there, and what is missing — including
integrations other document ORMs often advertise alongside the model layer.

You do not need experience with another framework to use it. Status meanings:

| Status | Meaning |
| --- | --- |
| **Shipped** | Ready to use |
| **Partial** | Works via a lower-level escape hatch; no first-class helper yet |
| **Missing** | Not available |
| **N/A** | Not applicable — Almasix chooses a different approach on purpose |

## Core document ORM

| Feature | Status | Notes |
| --- | --- | --- |
| Document models on collections | **Shipped** | `Document` extends `Model` |
| Config (`dsn`, database, host/port/user/pass, `options`) | **Shipped** | Same `config/database.py` as SQL |
| Mongo via Motor (`almasix[mongodb]`) | **Shipped** | Driver stays out of app signatures |
| Query builder (where, order, limit, CRUD, upsert, inc) | **Shipped** | `DocumentBuilder` |
| Embedded relationships | **Shipped** | `embeds_one` / `embeds_many` |
| Reference relationships | **Shipped** | Including cross-store links to SQL models |
| Soft deletes, factories, casts, events | **Shipped** | Inherited from Articulate |
| UUID / ULID keys | **Shipped** | Via `HasUuids` / `HasUlids` |
| Indexes declared on the model | **Shipped** | `indexes` + `documents:index` |
| Raw aggregation pipelines | **Partial** | `raw_aggregate`; no fluent Aggregation Builder |
| Text / `$text` helpers | **Partial** | Use `where_raw` / pipelines |
| Vector / Atlas Search helpers | **Missing** | SQL builder has vector helpers; documents do not |
| Many-to-many without pivot tables | **N/A** | Prefer id arrays or edge collections — no fake pivots |
| Schema Blueprint for collections | **N/A** | Indexes on the model instead |
| Cursor / keyset pagination | **Missing** | Offset and simple pagination ship |
| Multi-document transactions | **Missing** | Needs a replica set; `DB.transaction()` is SQL-only |
| In-memory document store | **Shipped** | First-class `memory` driver for tests and offline work |

## Framework integrations often bundled elsewhere

Some document ORMs also plug Mongo into cache, queues, files, or search. Almasix
does **not** claim these yet:

| Integration | Status |
| --- | --- |
| MongoDB cache driver (TTL indexes) | **Missing** — cache drivers are a separate subsystem |
| MongoDB queue driver | **Missing** |
| GridFS filesystem adapter | **Missing** — filesystem disks are separate |
| MongoDB Scout / full-text search engine | **Missing** — Scout has `database` / `collection` / Meilisearch |
| Third-party packages “just work” on Mongo | **Partial** — packages that use Articulate `Model` may; SQL-only packages will not |

Those belong in later releases if demand warrants them — not as footnotes
pretending to ship with `Document`.

## Deliberate design choices

- **Transactions.** Mongo multi-document transactions need a replica set.
  Almasix will not pretend a standalone node has them. Use SQL transactions,
  or redesign for single-document atomicity.
- **Keys.** Almasix does not wrap keys in a framework `ObjectId` type.
  Memory keys are hex strings; Mongo returns Motor's values. Prefer
  `get_key()` / `find` over assuming a Python `str` always.
- **Embeds save through the parent.** An embedded document has no collection;
  `save()` writes the parent field.
- **`memory` is a real store.** The same code path runs in CI and on a laptop
  with no Mongo — the document answer to an in-process SQL database.
- **Joins raise.** `UnsupportedQueryError` beats a silent wrong answer.

## Where to go next

- [Getting started](/articulate/documents/getting-started/) — install and config
- [Querying](/articulate/documents/querying/) — builder and refusals
- [Aggregations](/articulate/documents/aggregations/) — pipelines
