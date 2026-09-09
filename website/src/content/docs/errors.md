---
title: Error Handling
description: Exception Handler, polarity-aware pages, APP_DEBUG, and publishable error views.
---

## Handler

Unhandled exceptions pass through `almasix.exceptions.Handler` — `report(exc)` for logging via [`almasix.log`](/logging/) (`Log.info` / …), `render(request, exc)` for the HTTP response. Apps override at `app/exceptions/handler.py` (resolved from the container).

```python
# app/exceptions/handler.py
from almasix.exceptions import Handler as ExceptionHandler

class Handler(ExceptionHandler):
    dont_report: list[type[BaseException]] = []
```

## Polarity (not `Accept`)

| Route group | Response |
| --- | --- |
| `web` | HTML error page (or debug page when `APP_DEBUG`) |
| `api` | Locked JSON envelope `{message, status, errors?}` |

A web route that sends `Accept: application/json` still gets HTML. Put JSON clients on `api` routes.

**Unmatched routes** (no registered action): path convention — `/api/…` → JSON 404, everything else → HTML `errors/404`. Registered routes still use middleware-group polarity.

## Status mapping

Domain exceptions map to HTTP statuses before render. Built-ins include:

| Exception | Status |
| --- | --- |
| `ModelNotFoundError` | 404 |
| `ViewNotFoundError` | 404 |
| `ItemNotFoundError` | 404 |
| `TokenMismatchError` | 419 |
| `ServiceUnavailableHttpException` | 503 |

Extend at runtime with `register_status(MyError, 422)`.

## Debug vs production

The security gate is **`APP_DEBUG` only** (not `APP_ENV`):

- `APP_DEBUG=true` (web) — rich debug page with traceback and source excerpts
- `APP_DEBUG=false` (web) — `resources/views/errors/{status}.prism.html`
- Api — always JSON; debug only expands `message`, never embeds a stack trace

## Publishable views

```bash
python smith errors:publish
python smith errors:publish --bundle=tailwind
python smith errors:publish --bundle=bootstrap --force
```

Bundles: `default` (plain CSS), `tailwind`, `bootstrap`. `almasix new` ships the default set under `resources/views/errors/` (`404`, `419`, `429`, `500`, `503`).

## HttpException classes

| Class | Status |
| --- | --- |
| `BadRequestHttpException` | 400 |
| `UnauthorizedHttpException` | 401 |
| `ForbiddenHttpException` | 403 |
| `NotFoundHttpException` | 404 |
| `MethodNotAllowedHttpException` | 405 |
| `UnprocessableEntityHttpException` | 422 |
| `TooManyRequestsHttpException` | 429 |
| `ServiceUnavailableHttpException` | 503 |

Validation uses `ValidationException` (422 with `errors`). Default production copy lives in `lang/en/errors.py` (`errors.not_found`, …). Conversion still happens **inside** the middleware pipeline so route middleware can decorate error responses.

## `dump()` / `dd()`

Intentional debug halts use `from almasix import dump, dd` — not application errors. The Handler skips reporting `DumpAndDie` and renders a dedicated dump page (web HTML or api JSON) with status **200**. See [Smith Console](/console/#dump--dd).

## Related

- [Logging](/logging/)
- [Validation](/validation/)
- [Responses](/responses/)
