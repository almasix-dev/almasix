---
title: Queues
description: Jobs, sync and database drivers, workers, and failed jobs.
---

## Dispatching jobs

```python title="examples/queues.py"
from almasix.queue import Job, ShouldQueue, dispatch

class SendDigest(ShouldQueue, Job):
    tries = 3
    backoff = 10

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id

    def handle(self) -> None:
        ...

await dispatch(SendDigest(1))
await SendDigest.dispatch(user_id=1)
```

Jobs without `ShouldQueue` (and without `queue = True`) run synchronously. Use `dispatch_sync(job)` to force in-process execution.

## Drivers

| Connection | Driver | Notes |
| --- | --- | --- |
| `sync` | Immediate | Default for tests/dev |
| `database` | `jobs` / `failed_jobs` tables | Call `ensure_tables()` or migrate |
| `redis` | Redis lists + delayed ZSET | Requires `almasix[redis]`; see [Redis](/redis/) |

```python title="config/queue.py"
"redis": {
    "driver": "redis",
    "connection": "default",
    "queue": "queues",
},
```

```ini title="examples/queues.json"
QUEUE_CONNECTION=redis
```

## Workers

```bash title="terminal"
python smith queue:work
python smith queue:listen
python smith queue:failed
python smith queue:retry {id}
```

Failed jobs call `job.failed(exc)` and report through the exception Handler when available.

## Related

- [File Storage](/filesystem/)
- [Mail](/mail/) — queued mailables
- [Notifications](/notifications/) — queued notifications
