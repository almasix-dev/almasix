---
title: Asset Bundling
description: Vite, Tailwind, and serving CSS/JS from public/.
---

## Introduction

Almasix serves static files from your application’s `public/` directory.
`smith serve` mounts common public folders so browsers can load `/css/…`,
`/js/…`, `/images/…`, and `/build/…`.

Python core has **no Node dependency**. `almasix new` scaffolds one of four
frontend stacks — `tailwind` (the default), `bootstrap`, `plain`, or `none` —
and the first three compile through **Vite** into `public/build/`. The `none`
stack has no `package.json` at all: `public/css/app.css` is served as written.

## The stacks

| Stack | Entry points | Framework |
| --- | --- | --- |
| `tailwind` | `resources/css/app.css`, `resources/js/app.js` | Tailwind CSS 4 through `@tailwindcss/vite` |
| `bootstrap` | `resources/css/app.scss`, `resources/js/app.js` | Bootstrap 5, imported as Sass so its variables can be overridden |
| `plain` | `resources/css/app.css`, `resources/js/app.js` | none |
| `none` | `public/css/app.css` | none, and no build step |

```bash title="terminal"
npm install
npm run dev      # Vite development server (hot reload)
npm run build    # production assets → public/build
```

## `@vite`

Prism's `@vite` directive renders the tags for one or more entry points. It
takes a string, or a list:

```html title="resources/views/examples/asset-bundling.prism.html"
<head>
  <title>{{ name }}</title>
  @vite(['resources/css/app.css', 'resources/js/app.js'])
</head>
```

It resolves two different ways, and which one is in force depends on a single
file:

- **`public/hot` exists** — the Vite dev server is running, so the tags point at
  it and edits hot-reload. The scaffold's `vite-plugin-almasix.js` writes that
  file when the server starts listening and removes it when the server stops.
- **`public/hot` does not exist** — the tags come out of the manifest
  `npm run build` wrote, naming the hashed files it emitted. A stylesheet a
  listed JS entry imports is linked once, not twice.

```html title="resources/views/examples/asset-bundling.prism.html"
<!-- npm run dev -->
<script type="module" src="http://127.0.0.1:5173/@vite/client"></script>
<link rel="stylesheet" href="http://127.0.0.1:5173/resources/css/app.css"/>
<script type="module" src="http://127.0.0.1:5173/resources/js/app.js"></script>

<!-- npm run build -->
<link rel="stylesheet" href="/build/assets/app-1f2e3d.css"/>
<script type="module" src="/build/assets/app-4a5b6c.js"></script>
```

Every URL runs through `asset()`, so an application hosted under
`APP_BASE_PATH` links correctly without anything else being configured.

### When there is no build

An entry point the manifest does not name raises `ViteEntryNotFound`, naming
the entries it does have — a typo is an error, not a silently missing
stylesheet.

A missing manifest is treated differently, because there is an honest reason for
one: the application was just created and `npm run build` has not run yet. With
`APP_DEBUG=true`, `@vite` renders an HTML comment saying so. With debug off —
which is to say in production — it raises `ViteManifestNotFound`, because there
a missing build is a broken deploy.

### `@viteReactRefresh`

React's Fast Refresh needs a preamble before any component loads, and only in
development. `@viteReactRefresh` renders it while the dev server is running and
nothing at all otherwise:

```html title="resources/views/examples/asset-bundling.prism.html"
<head>
  @viteReactRefresh
  @vite('resources/js/app.jsx')
</head>
```

### From Python

The same resolution is available outside a template:

```python title="examples/asset-bundling.py"
from almasix.prism import Vite, vite

vite(["resources/css/app.css"])          # the tags, as a string
Vite().entry_url("resources/js/app.js")  # just the URL
Vite().dev_server_url()                  # the dev server's origin, or None
Vite().has_manifest()                    # whether a build is present
```

`Vite(base_path=…, build_directory="build", hot_file="public/hot")` covers the
cases where those are not the defaults.

## The `public` directory

You can also place finished assets directly under `public/`:

```text title="terminal"
public/
  css/app.css
  js/app.js
  images/logo.svg
  build/…          # Vite output
  hot              # written by the dev server; gitignored
```

## Generating asset URLs

Use `asset()` in Python or `@asset` / `asset()` inside Prism so
`APP_BASE_PATH` is applied:

```python title="routes/web.py"
from almasix.routing import asset

asset("css/app.css")
# → https://example.com/apps/progress/css/app.css  (when APP_BASE_PATH=/apps/progress)

asset("build/assets/app.css")
```

```html title="resources/views/examples/asset-bundling.prism.html"
<!-- resources/views/layouts/app.prism.html -->
<link rel="stylesheet" href="{{ asset('css/app.css') }}">
<script src="@asset('js/app.js')" defer></script>
```

`@asset('…')` is a Prism directive equivalent to printing `asset(...)`. Reach
for it for files you put under `public/` yourself, and for `@vite` for anything
a bundler emitted.

## Related

- [URL Generation](/urls/)
- [Views](/views/)
- [Prism stacks](/prism/stacks/) — `@push` scripts into layouts
- [Installation](/installation/)
