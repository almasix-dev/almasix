---
title: Middleware
description: Register and configure HTTP middleware in your Almasix application.
---

**Middleware** runs before (and sometimes after) a route handler. Use it to
inspect or change the request — start a session, reject guests, set a locale —
without repeating that logic in every controller.

Almasix registers middleware in **`bootstrap/app.py`**. Keep `config/http.py`
for group shells and defaults; put your application's wiring in the bootstrap
configurator.

## Registering middleware

```python title="bootstrap/app.py"
from pathlib import Path

from almasix.framework import Application, Middleware
from almasix.http import HEADER_X_FORWARDED_ALL
from almasix.translation import SetLocaleMiddleware

BASE_PATH = Path(__file__).resolve().parent.parent


def configure_middleware(middleware: Middleware) -> None:
    middleware.trust_proxies(at="*", headers=HEADER_X_FORWARDED_ALL)
    middleware.trust_hosts(at=["example.com", "*.example.com"])
    middleware.alias({"locale": SetLocaleMiddleware})
    middleware.web(append=["locale"])
    middleware.api(append=["locale"])


application = (
    Application.configure(BASE_PATH)
    .with_middleware(configure_middleware)
    .create()
)
asgi = application.asgi
```

Your ASGI entry point is `asgi` — deploy that with Uvicorn or any ASGI server.
Application code should not import FastAPI directly.

## Configurator API

| Method | Purpose |
| --- | --- |
| `alias({…})` | Bind short names for use on routes and groups |
| `web(append=…, prepend=…, replace=…)` | Middleware for the `web` group |
| `api(append=…, prepend=…, replace=…)` | Middleware for the `api` group |
| `group(name, …)` | Define any named group |
| `append` / `prepend` / `use` | Global stack (every request) |
| `trust_proxies(at=…, headers=…)` | Trust `X-Forwarded-*` from the given peers |
| `trust_hosts(at=…)` | Allowlist `Host` headers (others receive `400`) |

`trust_proxies` wraps the ASGI application so client IP, scheme, host, port, and
`root_path` reflect forwarded headers. `trust_hosts` prepends global middleware
that rejects disallowed hosts.

Header bitmasks are available from `almasix.http`
(`HEADER_X_FORWARDED_FOR`, `HEADER_X_FORWARDED_HOST`,
`HEADER_X_FORWARDED_PORT`, `HEADER_X_FORWARDED_PROTO`,
`HEADER_X_FORWARDED_PREFIX`, `HEADER_X_FORWARDED_ALL`,
`HEADER_X_FORWARDED_AWS_ELB`).

:::tip
Callbacks run after configuration is loaded and merge into `http.*`. In tests
you can still call `Application(base).bootstrap()` without the fluent builder.
:::

## Writing middleware

A middleware class exposes an async `handle` method that receives the request
and a `next` callable:

```python title="app/http/middleware/demo_tag_middleware.py"
class DemoTagMiddleware:
    async def handle(self, request, next):
        response = await next(request)
        # inspect or mutate response…
        return response
```

Generate a stub:

```bash title="terminal"
smith make:middleware DemoTagMiddleware
```

Then alias it in `bootstrap/app.py` and attach it to a group or route.
