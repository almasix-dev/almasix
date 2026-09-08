---
title: Asset Bundling
description: Vite, Tailwind, and serving CSS/JS from public/.
---

## Introduction

Almasix serves static files from your application’s `public/` directory.
`smith serve` mounts common public folders so browsers can load `/css/…`,
`/js/…`, `/images/…`, and `/build/…`.

Python core has **no Node dependency**. By default, `almasix new` scaffolds a
**Vite + Tailwind** frontend that compiles into `public/build/`. Starter kits
may replace or extend that toolchain; they are not required to get Vite.

## Default frontend toolchain

A fresh application includes:

```text
package.json
vite.config.js
resources/css/app.css
resources/js/app.js
public/build/          # npm run build output
```

```bash
npm install
npm run dev      # Vite development server (HMR)
npm run build    # production assets → public/build
```

Until a first-class `@vite` Prism directive lands, reference built files with
`asset()` after `npm run build`, or point at the Vite dev server while
`npm run dev` is running.

## The `public` directory

You can also place finished assets directly under `public/`:

```text
public/
  css/app.css
  js/app.js
  images/logo.svg
  build/…          # Vite output
```

## Generating asset URLs

Use `asset()` in Python or `@asset` / `asset()` inside Prism so
`APP_BASE_PATH` is applied:

```python
from almasix.routing import asset

asset("css/app.css")
# → https://example.com/apps/progress/css/app.css  (when APP_BASE_PATH=/apps/progress)

asset("build/assets/app.css")
```

```html
<!-- resources/views/layouts/app.prism.html -->
<link rel="stylesheet" href="{{ asset('css/app.css') }}">
<script src="@asset('js/app.js')" defer></script>
```

`@asset('…')` is a Prism directive equivalent to printing `asset(...)`.

## Related

- [URL Generation](/urls/)
- [Views](/views/)
- [Prism stacks](/prism/stacks/) — `@push` scripts into layouts
- [Installation](/installation/)
