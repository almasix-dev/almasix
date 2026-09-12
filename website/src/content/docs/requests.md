---
title: Requests
description: Inspect the incoming HTTP request with Almasix's Request bag.
---

**`Request`** is Almasix’s façade over the incoming ASGI request. Type-hint
`almasix.http.Request` in controllers — not the underlying Starlette request
type.

## Accessing the request

Inject `Request` into a controller action (or use a [`FormRequest`](/validation/),
which proxies to the same bag):

```python title="app/http/controllers/demo_controller.py"
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
| `validate(...)` | Validate the bag — schema or rule strings; see [Validation](/validation/) |


```python title="app/http/controllers/demo_controller.py"
request.input("email")
request.query("page", 1)
request.route("post")
request.merge({"source": "demo"})
request.validate(StoreItemRequest)  # raises 422 on failure
```

Path parameters stay out of `all()` / `input()` on purpose: a query string
cannot impersonate a path segment.

## Headers, cookies, and client metadata

```python title="app/http/controllers/demo_controller.py"
request.header("Accept")
request.cookie("theme")
request.bearer_token()
request.ip()
request.user_agent()
request.is_json()
request.is_method("POST")
```

When form method spoofing is on, `request.method` is the intended verb,
`request.real_method` is what actually arrived, and `request.spoofed_method`
is the `_method` value (or `None`). See [Routing](/routing/#form-method-spoofing).

## Files

```python title="app/http/controllers/demo_controller.py"
if request.has_file("avatar"):
    upload = request.file("avatar")
    data = await upload.read()
```

`UploadedFile` exposes `filename`, `content_type`, `size`, and async `read` /
`seek`. File storage disks are covered under [File Storage](/filesystem/);
until you wire a disk, handle bytes in the action or write to disk yourself.

## Related

- [Validation](/validation/) — FormRequest on top of this bag
- [Controllers](/controllers/)
- [Responses](/responses/)
- [Routing](/routing/) — path parameters and the current route
