---
title: Redis
description: Redis connections, façade, and cache / session / queue drivers.
---

## Introduction

Almasix talks to Redis through `almasix.redis`. Connections are configured in
`config/redis.py`. Cache, session, and queue can opt into Redis drivers while
keeping their local defaults for development.

Install the optional extra:

```bash title="terminal"
pip install 'almasix[redis]'
```

## Configuration

```python title="config/redis.py"
from almasix.config import env

config = {
    "default": env("REDIS_CLIENT", "default"),
    "connections": {
        "default": {
            "url": env("REDIS_URL"),
            "host": env("REDIS_HOST", "127.0.0.1"),
            "port": int(env("REDIS_PORT", 6379) or 6379),
            "database": int(env("REDIS_DB", 0) or 0),
            "password": env("REDIS_PASSWORD"),
            "username": env("REDIS_USERNAME"),
        },
    },
}
```

| Variable | Purpose |
| --- | --- |
| `REDIS_CLIENT` | Default connection name |
| `REDIS_URL` | Full URL (wins over host/port when set) |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` | Discrete connection settings |
| `REDIS_PASSWORD` / `REDIS_USERNAME` | Auth |

Cluster mode is not claimed yet — use a single connection.

## The `Redis` façade

```python title="examples/redis.py"
from almasix.redis import Redis, redis

Redis.set("greeting", b"hello", ex=60)
Redis.get("greeting")
Redis.delete("greeting")
Redis.incr("hits")
Redis.publish("orders", b"created")
pubsub = Redis.subscribe("orders")

client = redis()                 # async redis.asyncio client
client = Redis.connection()      # same
client = redis("default")
```

The façade methods are **sync wrappers** over the async client (same bridge
pattern as the database cache store). Prefer `await redis().get(...)` inside
async code when you already have an event loop.

## Cache driver

```python title="config/cache.py"
"redis": {
    "driver": "redis",
    "connection": "default",
}
```

```python title="examples/redis.py"
from almasix.cache import Cache

Cache.store("redis").put("users:1", user, 60)
Cache.store("redis").tags("users").put("ada", user, 60)
with Cache.store("redis").lock("deploy", seconds=10):
    ...
```

Tags and atomic locks are supported on Redis. Set `CACHE_STORE=redis` to make
it the default store.

## Session driver

```ini title="examples/redis.json"
SESSION_DRIVER=redis
```

```python title="config/session.py"
"driver": env("SESSION_DRIVER", "cookie"),
"connection": env("SESSION_CONNECTION", "default"),
"prefix": env("SESSION_PREFIX", "almasix_session:"),
```

The cookie then holds a signed session **id**; the payload lives in Redis under
the configured prefix. Default remains `cookie` for local apps.

## Queue driver

```python title="config/queue.py"
"redis": {
    "driver": "redis",
    "connection": "default",
    "queue": "queues",
},
```

```ini title="examples/redis.json"
QUEUE_CONNECTION=redis
```

Workers use the same `smith queue:work` entry point as the database driver.

## Related

- [Cache](/cache/)
- [Session](/session/)
- [Queues](/queues/)
- [Installation](/installation/)
