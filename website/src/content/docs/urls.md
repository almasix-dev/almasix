---
title: URL Generation
description: Build links that honor APP_URL and APP_BASE_PATH.
---

When an app is mounted under a subpath (`APP_BASE_PATH=/apps/progress`), every link and asset URL must include that prefix. Almasix's helpers centralize that rule.

## Configuration

| Env / config | Role |
| --- | --- |
| `APP_URL` | Origin (`https://example.com`) |
| `APP_BASE_PATH` | Public path prefix (`/apps/progress`) |

The HTTP kernel mounts the ASGI app at the same prefix so `smith serve` matches what `url()` emits.

## `url()`

```python
# app/http/controllers/welcome_controller.py
from almasix.routing import url

url("/progress")
# absolute:  {APP_URL}{APP_BASE_PATH}/progress
# relative:  url("/progress", absolute=False) → {APP_BASE_PATH}/progress
```

Already-absolute URLs (`https://…` or `//…`) are returned unchanged.

## `asset()`

Same prefixing for static files under `public/`:

```python
# app/http/controllers/welcome_controller.py
from almasix.routing import asset

asset("css/app.css")
```

See [Asset Bundling](/asset-bundling/).

## `redirect()`

```python
# app/http/controllers/welcome_controller.py
from almasix.http import redirect

return redirect("/progress")  # path resolved through url(..., absolute=False)
```

## Named routes

Per-route `name=` is accepted on the router today. A named-route `route("name", …)` helper is **planned** (Later / router DX). Until then, prefer `url("/explicit/path")`.

## In Prism

Templates receive `url` and `asset` automatically:

```html
<!-- resources/views/welcome.prism.html -->
<a href="{{ url('/progress') }}">Milestones</a>
<img src="{{ asset('images/almasix-banner.svg') }}" alt="Almasix">
```

## Related

- [Routing](/routing/)
- [Asset Bundling](/asset-bundling/)
- [Responses](/responses/)
