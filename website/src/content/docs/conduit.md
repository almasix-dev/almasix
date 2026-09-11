---
title: Conduit
description: Livewire 4–class reactive components for Almasix — Prism views, Alpine $wire, morph updates that feel like pure JS.
---

## Introduction

**Conduit** (`almasix.conduit`) is Almasix’s Livewire-class stack, targeting **Livewire 4**
semantics: server-driven components that render Prism templates, talk over a
CSRF-safe wire protocol, and interop with Alpine.js via `$wire`.

```python title="examples/conduit.py"
from almasix.conduit import Component, Conduit, conduit
```

The HTML attribute vocabulary stays **`wire:*`** (same as Livewire) so muscle
memory and docs transfer. The Python package is namespaced under Almasix —
not a top-level `flux` import. After installing, register a component and
browse a page that embeds it with `@conduit`.

:::note[Livewire 4 parity]
Every row in the [parity matrix](#livewire-4-parity-matrix) is **complete**
(`almasix.conduit.parity.PARITY`). Named deviations (e.g. signed update URLs —
stricter than Livewire) are documented on this page.
:::

## Installation

Conduit ships inside the `almasix` distribution (like Signet):

```bash title="terminal"
pip install 'almasix[conduit]'   # extra reserved; currently zero extra deps
```

`ConduitServiceProvider` boots with the framework foundation providers. Publish
optional config/assets:

```bash title="terminal"
smith vendor:publish --tag=conduit-config
smith vendor:publish --tag=conduit-assets
```

## Quick start

```python title="app/conduit/counter.py"
from almasix.conduit import Component

class Counter(Component):
    count = 0

    def increment(self) -> None:
        self.count += 1

    def render(self) -> str:
        return "conduit.counter"
```

```html title="resources/views/examples/conduit.prism.html"
<!-- resources/views/conduit/counter.prism.html -->
<div>
  <h1 wire:text="count">{{ count }}</h1>
  <button type="button" wire:click="increment" data-loading>+</button>
  <input type="text" wire:model.live="label">
  <span wire:text="label">{{ label }}</span>
</div>
```

```html title="resources/views/examples/conduit.prism.html"
<!-- layout -->
@conduitScripts
@conduit('counter')
```

```python title="examples/conduit.py"
from almasix.conduit import conduit
from almasix.prism.helpers import view

def show():
    return view("page", {"body": conduit("counter")})
```

## Why it can feel like pure JS

Conduit optimizes the **happy path** so typing and toggles do not wait on the
network for visual feedback:

1. **Client bindings** — `wire:text`, `wire:show`, and `wire:bind:*` update from
   `$wire` / `serverMemo.data` immediately after optimistic local writes.
2. **Request coalescing** — updates/calls within ~16ms merge into one
   `POST /conduit/update` (Livewire-style batching).
3. **Idiomorph-lite morph** — patches attributes and keyed children instead of
   blindly replacing the root (respects `wire:ignore` / `wire:key`).
4. **Islands** — `wire:island` / `$wire.$island()` scopes HTML morph to a
   region so the rest of the component stays put.
5. **`.renderless`** — skip HTML when only server state / events matter.
6. **`data-loading`** — v4-style loading hooks for CSS without extra roundtrips.

Use `wire:model.live` + `wire:text` on the same property for an input that feels
instant while still syncing to the server.

## Components

### Public state

Class attributes that are not methods become public properties (snapshotted,
checksummed, syncable):

```python title="examples/conduit.py"
class Search(Component):
    query = ""
    page = 1
    query_string = ["query", "page"]
```

### Lifecycle

| Hook | When |
| --- | --- |
| `mount()` | First create |
| `hydrate()` | After snapshot restore |
| `booted()` | After mount/hydrate |
| `dehydrate()` | Before snapshot |
| `rendering()` / `rendered(html)` | Around Prism render |

### Actions

```python title="examples/conduit.py"
def save(self) -> None:
    self.validate()
    self.dispatch("saved", id=self.id)

def quiet(self) -> None:
    self.do_work()
    self.renderless()  # no HTML morph
```

Call from the browser with `wire:click="save"`, `wire:click="add(1)"`, or
`$wire.save()`.

### Validation

```python title="app/models/example.py"
from pydantic import BaseModel, Field

class Rules(BaseModel):
    label: str = Field(min_length=1)

class Form(Component):
    label = ""
    rules = Rules

    def save(self) -> None:
        self.validate()
```

Errors land in `component.errors` / `$errors` / `effects.errors`.

### Nested components

```html title="resources/views/examples/conduit.prism.html"
@conduit('counter')
@conduit('forms.profile', user_id=user.id)
```

### Lazy / defer

```python title="examples/conduit.py"
class Heavy(Component):
    lazy = True           # load when scrolled into view
    # defer = True        # load on next frame after paint
    lazy_placeholder = "conduit.placeholders.spinner"
```

## Wire protocol

### Endpoint

`POST /conduit/update` (web middleware: session + CSRF + **`signed:relative`**).
Clients must use the signed URL from `@conduitScripts` / `effects.endpoint` —
see [Signed update requests](#signed-update-requests).

Send `X-CSRF-TOKEN` (or `_token`) and JSON:

```json title="examples/conduit.json"
{
  "fingerprint": { "id": "...", "name": "counter" },
  "serverMemo": { "data": { "count": 0 }, "checksum": "...", "errors": {} },
  "updates": [["count", 1]],
  "calls": [{ "method": "increment", "params": [] }],
  "island": null
}
```

Response effects may include `html`, `islands`, `data`, `errors`, `dispatches`,
`queryString`. The client applies `data` bindings **before** morphing so the UI
moves first.

### Checksums

Snapshots HMAC with `conduit.checksum_key` or `app.key`. Tampered memos are
rejected.

### Assets

`/conduit/conduit.js` plus Alpine (CDN configurable via `conduit.alpine_cdn`).
Prefer bundling Alpine yourself and loading only Conduit’s script in production.

## Directives (Livewire vocabulary)

### Actions

| Directive | Notes |
| --- | --- |
| `wire:click="method"` | Also `method(1, 'x')` |
| `wire:click.renderless` | Skip HTML |
| `wire:click.preserve-scroll` | Keep scrollY |
| `wire:submit="save"` | Prevents default |
| `wire:init="boot"` | Fire once on boot |
| `wire:confirm="…"` | `window.confirm` before action |
| `wire:poll` / `wire:poll.5s` | Interval refresh |
| `wire:intersect` | Viewport enter (+ `.once` / `.half` / `.full`) |
| `wire:island="name"` | Scope the action’s morph |

### Binding

| Directive | Notes |
| --- | --- |
| `wire:model` | Sync on change |
| `wire:model.live` | Sync on input (coalesced) |
| `wire:model.blur` | Sync on blur (v4 client sync timing) |
| `wire:model.live.blur` | Live client + blur network |
| `wire:model.debounce.300ms` | Debounced live |
| `wire:model.deep` | Listen to bubbled child events |
| `wire:text="prop"` | **Client** textContent from memo |
| `wire:show="prop"` | **Client** display toggle |
| `wire:bind:class="…"` | **Client** reactive attribute (v4) |
| `wire:bind:disabled="…"` | Expressions see `data` / `$wire` |

### DOM / loading

| Directive | Notes |
| --- | --- |
| `wire:loading` / `data-loading` | Loading affordances |
| `wire:dirty` | Dirty class while in-flight |
| `wire:ignore` | Skip morph subtree |
| `wire:key` | Morph identity in lists |
| `wire:ref="name"` | `$el.__conduitRefs.name` |
| `wire:sort` + `wire:sort:item` | Basic HTML5 DnD → method(order) |
| `wire:navigate` | Partial SPA visit + View Transitions when available |

## Alpine `$wire`

```html title="resources/views/examples/conduit.prism.html"
<button @click="$wire.increment()">+</button>
<span x-text="$wire.count"></span>
```

Magics: `$wire`, `$errors`. Helpers: `$wire.$set`, `$toggle`, `$refresh`,
`$dispatch`, `$island('stats')`.

## Islands (Livewire 4)

Mark a region:

```html title="resources/views/examples/conduit.prism.html"
<div wire:island="stats">
  <p wire:text="visits">{{ visits }}</p>
</div>
<button wire:click="refreshStats" wire:island="stats">Refresh</button>
```

Or declare island views on the component:

```python title="examples/conduit.py"
class Dashboard(Component):
    island_views = {"stats": "conduit.dashboard.stats"}
```

Only that island’s HTML is applied when the request targets it.

## Signed update requests

Every `POST /conduit/update` must present a **valid relative signature**
(`signed:relative`). This is stricter than a client-side snapshot checksum
alone:

1. `@conduitScripts` embeds a short-lived signed endpoint in
   `window.__CONDUIT__.endpoint` / `<meta name="conduit-endpoint">`.
2. The route carries `middleware=["signed:relative"]`.
3. Each successful update rotates `effects.endpoint` so long-lived tabs stay
   fresh.
4. Signatures cover the **internal** path (`/conduit/update?expires&signature`);
   `APP_BASE_PATH` is prefixed only for the browser — so subpath mounts keep
   verifying correctly.

Bare `/conduit/update` without a signature returns **403**. CSRF still applies
(419 when the session token is missing).

Config: `conduit.signature_ttl_minutes` (default 720).

## Subpath hosting (`APP_BASE_PATH`)

Serving interactive components under a public prefix (`/my-app`, `/apps/foo`)
is a common footgun. Conduit is built on Almasix’s existing subpath story:

1. Route URIs stay unprefixed (`POST /conduit/update`) inside the app.
2. The HTTP kernel mounts ASGI at `APP_BASE_PATH` (`almasix.http.subpath`).
3. `@conduitScripts` emits **prefixed** URLs via `url()` and an inline
   `window.__CONDUIT__ = { base, endpoint, asset }` plus
   `<meta name="conduit-endpoint">` / `conduit-base`.
4. The JS client **never** hardcodes `/conduit/update`. It reads that boot
   config (or derives the prefix from the script `src`), and `withBase()`
   guards `wire:navigate` / root-absolute paths.

```bash title="terminal"
# .env
APP_BASE_PATH=/my-app
```

Then the browser posts to `/my-app/conduit/update` and loads
`/my-app/conduit/conduit.js`. Confirm those URLs in DevTools after setting
`APP_BASE_PATH`.

## Configuration

```python title="config/conduit.py"
config = {
    "endpoint": "/conduit/update",
    "asset_url": "/conduit/conduit.js",
    "inject_assets": True,
    "checksum_key": None,
    "signature_ttl_minutes": 720,
    "alpine_cdn": "https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js",
    "coalesce_ms": 16,
    "csp_safe": False,
}
```

## Livewire 4 parity matrix

All rows **complete**. Machine source: `almasix.conduit.parity.PARITY`.

| Feature | Status |
| --- | --- |
| wire:click (+ params, async/renderless/preserve-scroll) | complete |
| wire:model / .live / .blur / .change / .debounce / .deep | complete |
| wire:submit | complete |
| snapshot + checksum + CSRF | complete |
| **signed update URLs (HMAC + expiry)** | complete |
| request coalescing | complete |
| idiomorph-lite morph + wire:key / ignore | complete |
| Alpine $wire + $errors | complete |
| wire:text / wire:show / wire:bind (client) | complete |
| **APP_BASE_PATH / subpath hosting** | complete |
| nested `@conduit` | complete |
| validation errors | complete |
| events / $dispatch / $js / $entangle | complete |
| wire:loading + data-loading | complete |
| wire:dirty / ignore / poll / init / confirm | complete |
| lazy / defer | complete |
| file uploads | complete |
| query-string binding | complete |
| wire:intersect / wire:ref / wire:sort | complete |
| wire:island scoped updates | complete |
| wire:navigate + View Transitions | complete |
| wire:offline / wire:online | complete |
| inline HTML `render()` (SFC-style) | complete |
| Route.conduit() full-page components | complete |
| WithPagination / Computed / Locked / On | complete |
| CSP-safe Alpine (`conduit.csp_safe`) | complete |
| `smith make:conduit` | complete |

## Starter kits

Web starter kits will consume Conduit for interactive islands. Kits are **later** —
Conduit itself is exhausted.

## Extract

Published as [`almasix-conduit`](https://pypi.org/project/almasix-conduit/)
from [`almasix-dev/conduit`](https://github.com/almasix-dev/conduit).
Install with `pip install 'almasix[conduit]'`. Import path stays
`from almasix.conduit import …`. The provider is discovered via the
`almasix.providers` entry-point group.
