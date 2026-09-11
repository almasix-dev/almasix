---
title: Documentation Versions
description: Major-version docs switching — latest major by default, main for unreleased.
---

## How versions work

The docs header switcher lists **major lines** and **`main`**, never every
minor tag:

| Switcher label | Meaning |
| --- | --- |
| **0.x** | Docs for the 0.x package line — **latest** (default) |
| **main** | Unreleased tip from the `main` branch (opt-in) |
| **1.x** *(later)* | Docs for the 1.x package line, once that major ships |

**Latest is always the newest major** (`0.x` today). `main` is never the
default. Minor releases (`0.3.0`, `0.4.0`, …) are recorded in
[Release Notes](/prologue/release-notes/) and the [Upgrade Guide](/prologue/upgrade/),
not as separate documentation trees.

## Not on latest

If you open a line that is not the latest major — including **`main`** — a
banner appears with a link back to the latest documentation.

| Package | Docs switcher |
| --- | --- |
| `almasix==0.*` | `0.x` (latest) |
| Working from unreleased `main` | `main` |
| `almasix==1.*` *(later)* | `1.x` |

## Parallel trees

Today the site is a single corpus. Selecting a non-latest line sets
`?docsVersion=` so the switcher and banner stay in sync in the browser. When
**1.x** ships, archived major trees (`/0.x/…`, `/1.x/…`) will hold frozen page
sets — same switcher behaviour, with real path prefixes.
