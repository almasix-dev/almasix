---
title: Logging
description: Log channels and the Log façade — wired to the exception Handler.
---

## Import from `almasix.log`

Application logging lives in **`almasix.log`**, not Python's stdlib `logging`
module. The names look similar; the APIs do not:

```python title="examples/logging.py"
# Correct — Almasix façade (autocomplete: info, debug, success, …)
from almasix.log import Log

Log.info("Application started")

# Wrong — stdlib. `logging.log` requires a level and has no Log.info / success.
import logging
logging.log(...)   # not what you want in an Almasix app
```

Prefer the `Log` façade (`Log.info(...)`, `Log.error(...)`, and friends).

## Writing log lines

```python title="database/migrations/example_migration.py"
from almasix.log import Log

Log.info("Application started")
Log.debug("cache miss", extra={"key": "users.1"})
Log.warning("Something odd")
Log.error("Checkout failed")
Log.success("Migration finished")
Log.channel("stderr").warning("noisy channel")
Log.with_(request_id="abc", user_id=7).info("Checked out")
```

There is also a function form — `from almasix.log import log` then
`log().info(...)` — which is the same writer. Prefer `Log` in application
code so editors resolve the façade methods.

| Method | Severity |
| --- | --- |
| `debug` | DEBUG |
| `info` / `notice` | INFO |
| `success` | SUCCESS (between info and warning) |
| `warning` | WARNING |
| `error` / `exception` | ERROR (`exception` attaches a traceback) |
| `critical` / `alert` / `emergency` | CRITICAL |

## Configuration

`config/logging.py` declares the default channel and named drivers:

| Driver | Role |
| --- | --- |
| `stack` | Fan-out to other channel names |
| `single` | One file under `storage/logs/` |
| `daily` | Timed rotating file |
| `stderr` | Stream to stderr |
| `null` | Discard (tests) |

A fresh app defaults to the `stack` → `single` channel, so the first
`Log.info(...)` creates `storage/logs/almasix.log`.

## Exception reporting

`Handler.report()` writes through the logger. Client `HttpException` responses (`status < 500`) are not reported by default; 5xx and unhandled exceptions are.

## Related

- [Error Handling](/errors/)
- [Helpers](/helpers/) (`info()`, `logger()`)
