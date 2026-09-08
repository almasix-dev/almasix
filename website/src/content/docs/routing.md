---
title: Routing
description: Define web and API routes with Almasix's Route DSL.
---

Routes map HTTP verbs and URIs to controller actions. Almasix splits **browser** and **API** surfaces: `routes/web.py` returns HTML; `routes/api.py` returns JSON.

Register routes with the `Route` façade from `almasix.routing`. Controllers are resolved from the container — never import FastAPI in application code.

## Basic routing

```python
# routes/web.py
from app.http.controllers.welcome_controller import WelcomeController

from almasix.routing import Route

Route.get("/", [WelcomeController, "index"])
Route.post("/posts", [WelcomeController, "store"])
```

Supported verbs: `get`, `post`, `put`, `patch`, `delete`, `options`, `any`, and `match([...], uri, action)`.

Actions may be `[Controller, "method"]`, a callable, or `"Controller@method"`.

## Route polarity

| File | Audience | Default response | Middleware group |
| --- | --- | --- | --- |
| `routes/web.py` | Browsers | HTML | `web` |
| `routes/api.py` | Clients / SPAs | JSON | `api` |

```python
# routes/web.py
with Route.group(middleware=["web"]):
    Route.get("/", [WelcomeController, "index"])

# routes/api.py
with Route.group(prefix="/api", middleware=["api"]):
    Route.get("/health", [HealthController, "index"])
```

The `web` group runs session start, cookie encryption, CSRF, and auth hydration. The `api` group stays stateless (bearer via `auth.start` only).

## Groups

Groups are **context-manager only** (no fluent `Route.middleware(...).group(...)` chain):

```python
# routes/api.py
with Route.group(prefix="/api", middleware=["api"]):
    Route.get("/health", [HealthController, "index"])

    with Route.group(prefix="/items"):
        Route.get("/{item}", [DemoController, "show"])
        Route.post("", [DemoController, "store"])
```

Nested groups concatenate prefixes and accumulate middleware outer → inner. Group middleware may name a **middleware group** (`web` / `api`) or an alias registered in `bootstrap/app.py`.

## Route parameters

```python
# routes/web.py
Route.get("/posts/{post}", [PostController, "show"])
```

Path parameters are available on the request via `request.route("post")` (they are **not** merged into `all()` / `input()`).

## Per-route options

```python
# routes/web.py
Route.get("/ping", [DemoController, "ping"], name="ping", middleware=["locale"])
```

Named-route URL generation (`route("ping")`) is planned; today use [`url()`](/urls/) with explicit paths.

## Related

- [Middleware](/middleware/) — aliases, `web` / `api` stacks
- [Controllers](/controllers/) — actions and DI
- [URL Generation](/urls/) — `url()`, `asset()`, `redirect()`
