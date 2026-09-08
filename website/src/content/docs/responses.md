---
title: Responses
description: Return HTML, JSON, redirects, and other HTTP responses.
---

Controller actions may return several shapes. The HTTP kernel normalizes them into ASGI responses.

## Return values

| Return | Result |
| --- | --- |
| `dict` / `list` | JSON (`application/json`) |
| `str` | Plain text |
| `bytes` | Raw body |
| `None` | `204` (or the status you pass to helpers) |
| A response object | Used as-is |

Prefer explicit helpers when the intent matters:

```python
# app/http/controllers/welcome_controller.py
from almasix.http import html, json, redirect
from almasix.prism import view


async def index(self):
    return view("welcome", {"name": "Ada"})


async def data(self):
    return json({"ok": True})


async def legacy_markup(self):
    return html("<h1>Hi</h1>")


async def leave(self):
    return redirect("/progress")
```

## Web vs API polarity

- **Web routes** (`routes/web.py`) should return Prism views or `html(...)`.
- **API routes** (`routes/api.py`) should return `dict` / `list` / `json(...)`.

Throwing an [`HttpException`](/errors/) on an API route still yields the locked JSON envelope `{message, status, errors?}`.

## Redirects

`redirect(to)` resolves `to` through [`url()`](/urls/) so `APP_BASE_PATH` is honored:

```python
# app/http/controllers/welcome_controller.py
return redirect("/dashboard")  # → /apps/progress/dashboard when mounted
```

## Headers and status

```python
# app/http/controllers/welcome_controller.py
return json({"ok": True}, status=201, headers={"X-Demo": "1"})
return html("<p>Gone</p>", status=410)
```

## Related

- [Views](/views/) — Prism templates
- [URL Generation](/urls/)
- [Error Handling](/errors/)
