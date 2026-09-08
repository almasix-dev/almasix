---
title: Requests
description: Inspect the incoming HTTP request with Almasix's Request bag.
---

Almasix's `Request` is the application façade over the ASGI request. Application code should type-hint `almasix.http.Request`, not Starlette/FastAPI request types.

## Accessing the request

Inject `Request` into a controller action (or use a [`FormRequest`](/validation/), which proxies to the same bag):

```python
# app/http/controllers/demo_controller.py
from almasix.http import Controller, Request


class DemoController(Controller):
    async def echo_bag(self, request: Request) -> dict:
        return {
            "all": request.all(),
            "only": request.only("q", "page"),
            "path": request.path,
            "method": request.method,
        }
```

## Input bags

| Method | Meaning |
| --- | --- |
| `all()` / `input()` | Query string **merged with** body (body wins) |
| `query()` | Query string only |
| `post()` | Body only (JSON object or form fields) |
| `json()` | Parsed JSON payload |
| `route()` | Path / route parameters (**not** in `all()`) |
| `only(...)` / `except_(...)` | Subset of the merged input |
| `has` / `has_any` / `filled` / `missing` | Presence helpers |
| `boolean` / `integer` / `float` / `string` | Coercion helpers |

```python
# app/http/controllers/demo_controller.py
request.input("email")
request.query("page", 1)
request.route("post")
request.merge({"source": "demo"})
```

## Headers, cookies, and client metadata

```python
# app/http/controllers/demo_controller.py
request.header("Accept")
request.cookie("theme")
request.bearer_token()
request.ip()
request.user_agent()
request.is_json()
request.is_method("POST")
```

## Files

```python
# app/http/controllers/demo_controller.py
if request.has_file("avatar"):
    upload = request.file("avatar")
    data = await upload.read()
```

`UploadedFile` exposes `filename`, `content_type`, `size`, and async `read` / `seek`. Storage disks arrive in a later milestone; until then handle bytes in the action or write to disk yourself.

## Related

- [Validation](/validation/) — FormRequest on top of this bag
- [Controllers](/controllers/)
- [Responses](/responses/)
