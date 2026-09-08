---
title: Logging
description: Log channels and the log() helper — wired to the exception Handler.
---

## Configuration

`config/logging.py` declares the default channel and named drivers:

| Driver | Role |
| --- | --- |
| `stack` | Fan-out to other channel names |
| `single` | One file under `storage/logs/` |
| `daily` | Timed rotating file |
| `stderr` | Stream to stderr |
| `null` | Discard (tests) |

```python
from almasix.log import log

log().info("Application started")
log("stderr").warning("Something odd")
log().with_(request_id="abc", user_id=7).info("Checked out")
log().with_context({"job": "mail"}).error("Failed")
```

## Exception reporting

`Handler.report()` writes through the logger. Client `HttpException` responses (`status < 500`) are not reported by default; 5xx and unhandled exceptions are.

## Related

- [Error Handling](/errors/)
