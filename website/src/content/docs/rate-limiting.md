---
title: Rate Limiting
description: Cache-backed RateLimiter, throttle middleware, and login throttling.
---

Almasix rate-limits anything that needs a budget — HTTP routes, login attempts,
or an arbitrary callback — with a thin counter over the application cache. The
shape matches Laravel's [Rate Limiting](https://laravel.com/docs/rate-limiting)
and the `throttle` middleware documented under Routing.

## Cache configuration

By default the limiter uses the application's default cache store. Point it at
a dedicated store (typically Redis in production) with the `limiter` key in
`config/cache.py`:

```python
config = {
    "default": env("CACHE_STORE", "file"),
    "limiter": env("CACHE_LIMITER_STORE", "redis"),
    # ...
}
```

In code, this is surfaced as `cache.limiter` (a Laravel-shaped config key) so
`RateLimiter` can pick the correct store for its counters.

Counters live under the `almasix:rate:` key prefix. Queue workers and HTTP
processes that share that cache store also share the same budgets — the same
reason Laravel asks you to pick Redis for production rate limiting.

## Basic usage

```python
from almasix.http import RateLimiter

executed = RateLimiter.attempt(
    f"send-message:{user.id}",
    5,
    lambda: send_message(),
)

if not executed:
    return "Too many messages sent!"
```

`attempt` returns `False` when the key is exhausted; otherwise it returns the
callback's result (or `True` when the callback returns `None`). Pass a fourth
argument to change the window from the default sixty seconds:

```python
RateLimiter.attempt(f"send-message:{user.id}", 5, send_message, decay_seconds=120)
```

### Manual increments

```python
if RateLimiter.too_many_attempts(f"send-message:{user.id}", 5):
    seconds = RateLimiter.available_in(f"send-message:{user.id}")
    return f"Try again in {seconds} seconds."

RateLimiter.hit(f"send-message:{user.id}")
# or RateLimiter.increment(key, decay_seconds=60, amount=5)
```

`remaining` / `retries_left`, `clear`, and `reset_attempts` round out the
surface. CamelCase aliases (`tooManyAttempts`, `availableIn`, …) are installed
for readers coming from Laravel docs.

## Defining rate limiters

Register named limiters in a service provider — the scaffold's
`AppServiceProvider` already registers an `api` limiter:

```python
from almasix.http import Limit, RateLimiter

RateLimiter.for_("api", lambda request: Limit.per_minute(60).by(
    request.user().id if request.user() else request.ip()
))
```

`for` is a Python keyword, so the method is `for_` (also available as
`RateLimiter.for_name` and as the attribute `RateLimiter.for`). A limiter may
return one `Limit`, a list of limits, or `None` / `Limit.none()` to skip
throttling for that request.

### Limit factories

| Factory | Window |
| --- | --- |
| `Limit.per_second(n)` | 1 second |
| `Limit.per_minute(n)` | 60 seconds |
| `Limit.per_hour(n)` | 3600 seconds |
| `Limit.per_day(n)` | 86400 seconds |
| `Limit.none()` | unlimited |

Chain `.by(key)`, `.response(callback)`, and `.after(callback)`:

```python
RateLimiter.for_("uploads", lambda request: [
    Limit.per_minute(10).by(f"minute:{request.user().id}"),
    Limit.per_day(1000).by(f"day:{request.user().id}"),
])

RateLimiter.for_("resource-not-found", lambda request:
    Limit.per_minute(10)
    .by(request.ip())
    .after(lambda response: getattr(response, "status_code", 0) == 404)
)

RateLimiter.for_("global", lambda request:
    Limit.per_minute(1000).response(
        lambda request, headers: JSONResponse(
            {"message": "Slow down."}, status_code=429, headers=headers
        )
    )
)
```

## Attaching rate limiters to routes

```python
Route.get("/audio", upload, middleware=["throttle:uploads"])
Route.get("/burst", handler, middleware=["throttle:60,1"])  # 60 / minute
Route.get("/mixed", handler, middleware=["throttle:10|60"])  # guest|auth
```

`throttle:60,1` is max attempts, then decay in **minutes**. A bare `throttle:60`
is sixty per minute. `throttle:10|60` uses ten for guests and sixty for
authenticated users.

Put the named `api` limiter on every API route the Laravel 11 way:

```python
def configure(middleware: Middleware) -> None:
    middleware.throttle_api()  # prepends throttle:api to the api group
```

Successful responses carry `X-RateLimit-Limit` and `X-RateLimit-Remaining`. A
refusal is a `429 Too Many Attempts.` with `Retry-After` and
`X-RateLimit-Reset`.

## Login throttling

Wire login the same way Laravel's `LoginRequest` does:

```python
from almasix.auth import LoginRateLimiter, attempt_login

limiter = LoginRateLimiter(max_attempts=5, decay_seconds=60)

# Or the one-liner that hits on failure and clears on success:
ok = await attempt_login(
    {"email": email, "password": password},
    request=request,
    remember=remember,
)
```

When the budget is spent, `LoginRateLimiter.raise_for` (and `attempt_login`)
raise `TooManyRequestsHttpException` with the translated `auth.throttle`
message and a `Retry-After` header.

## Living example

```bash
smith progress:rate-limiting
```

The progress app also exposes `/api/throttle-demo` behind `throttle:progress`
(three hits per minute) so a browser or `curl` can watch the 429 land.
