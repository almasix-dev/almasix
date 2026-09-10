---
title: Inertia
description: Server-side Inertia.js adapter for official Vue, React, and Svelte clients — protocol, SSR, and prop helpers.
---

## Introduction

**almasix-inertia** is a **server-only** adapter. Use the official
`@inertiajs/vue3`, `@inertiajs/react`, or `@inertiajs/svelte` clients — there is
**no forked JS client**. SSR uses Inertia’s Node `/render` protocol.

```bash
pip install -e packages/inertia
# register inertia.provider.InertiaServiceProvider (Progress already does)
```

```python
from inertia import Inertia, lazy, defer, once, merge
```

Progress: `smith progress:inertia`, `GET /inertia`, `smith inertia:start-ssr --check`.

## Rendering

```python
def dashboard():
    return Inertia.render("Dashboard", {
        "user": user,
        "stats": lazy(lambda: expensive_stats()),
        "notes": defer(lambda: load_notes()),
    })
```

| Visit type | Response |
| --- | --- |
| First (no `X-Inertia`) | Root Prism template with `@inertia` / `@inertiaHead` |
| Inertia (`X-Inertia: true`) | JSON page object |
| Version mismatch | `409` + `X-Inertia-Location` |
| External redirect | `Inertia.location(url)` → `409` + `X-Inertia-Location` |

The page `url` is built with `url()` so **`APP_BASE_PATH` is honored**.

## Shared props

```python
Inertia.share("app_name", config("app.name"))
Inertia.share(lambda: {"auth": {"user": current_user()}})
```

Session flash `errors` is merged into props when present.

## Partial reloads

Headers:

- `X-Inertia-Partial-Component`
- `X-Inertia-Partial-Data` (comma list)
- `X-Inertia-Partial-Except`

## Prop helpers

| Helper | Behavior |
| --- | --- |
| `Inertia.lazy` / `lazy()` | Omitted unless requested in a partial |
| `Inertia.optional` / `optional()` | Same as lazy |
| `Inertia.defer` / `defer()` | Listed in `deferredProps` for client follow-up |
| `Inertia.once` / `once()` | Evaluated once per response object |
| `Inertia.merge` / `merge()` | Listed in `mergeProps` for client merge |

## Asset versioning

```python
Inertia.set_version("v42")
# or config inertia.version
```

Middleware `HandleInertiaRequests` (alias `inertia`) compares
`X-Inertia-Version` and forces a full reload on mismatch.

## SSR

1. Use or copy `packages/inertia/src/inertia/ssr/server.js`
2. `smith inertia:start-ssr` (or `node bootstrap/ssr.js`)
3. `inertia.ssr_enabled = True`, `inertia.ssr_url = "http://127.0.0.1:13714"`

If the worker is down, the adapter falls back to the client-only shell
(`ssr_body` / `ssr_head` empty).

Smoke: with the worker up, first HTML contains both page JSON and SSR markup.

## Root template

```html
<!DOCTYPE html>
<html>
<head>
  @inertiaHead
  @vite(['resources/js/app.jsx'])
</head>
<body>
  @inertia
</body>
</html>
```

## Exhaust checklist

- [x] `Inertia.render` Responsable (`to_response`)
- [x] `X-Inertia` JSON visits
- [x] Shared + partial props
- [x] Lazy / optional / defer / once / merge props
- [x] Asset version 409
- [x] `Inertia.location` external visits
- [x] Flash errors → props
- [x] Subpath-aware page `url`
- [x] `@inertia` / `@inertiaHead`
- [x] Node SSR contract + graceful fallback
- [x] `inertia:start-ssr`
- [x] Progress demo + smoke

## Starter kits

SPA starter kits consume this adapter plus an official `@inertiajs/*` client.
Extract target: `almasix-dev/inertia` (see `packages/inertia/EXTRACT.md`).
