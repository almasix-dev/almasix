---
title: Cache
description: Cache stores, remembering values, atomic locks, and tags.
---

## Introduction

Almasix’s cache layer stores temporary data behind a single façade. Use it to
memoize expensive work, share short-lived state between requests, and take
cross-process locks for scheduled tasks or jobs.

```python title="examples/cache.py"
from almasix.cache import Cache, cache

Cache.put("users:1", {"name": "Ada"}, 60)
user = Cache.get("users:1")
Cache.remember("stats:home", 120, lambda: compute_stats())
```

## Configuration

Scaffolded apps ship `config/cache.py`. The default store and key prefix come
from the environment:

### Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `CACHE_STORE` | `file` | Name of the default store (`array`, `file`, `database`, `null`, …) |
| `CACHE_PREFIX` | `almasix_cache_` | Prefix applied to every cache key |

```ini title="examples/cache.json"
CACHE_STORE=file
CACHE_PREFIX=almasix_cache_
```

```python title="config/cache.py"
from almasix.config import env

config = {
    "default": env("CACHE_STORE", "file"),
    "prefix": env("CACHE_PREFIX", "almasix_cache_"),
    "stores": {
        "array": {"driver": "array"},
        "file": {
            "driver": "file",
            "path": "storage/framework/cache/data",
        },
        "database": {
            "driver": "database",
            "connection": None,
            "table": "cache",
            "lock_table": "cache_locks",
        },
        "redis": {
            "driver": "redis",
            "connection": "default",
        },
        "null": {"driver": "null"},
    },
}
```

### Choosing a store

| Store | When to use it |
| --- | --- |
| **array** | Process-local only — ideal for tests and demos (progress defaults here) |
| **file** | Single-server apps; data under `storage/framework/cache/data` |
| **database** | Shared cache across app processes via Articulate (`cache` + `cache_locks` tables) |
| **redis** | Shared cache via Redis (`almasix[redis]`) — tags and locks supported |
| **null** | Disable caching without removing call sites (writes accepted, reads miss) |

```python title="examples/cache.py"
Cache.store("redis").put("logo", svg, 3600)
Cache.store("redis").tags("assets").put("logo", svg, 3600)
```

See [Redis](/redis/) for connection configuration.

Switch stores per call:

```python title="examples/cache.py"
Cache.store("file").put("logo", svg, 3600)
Cache.store("database").get("logo")
```

## Retrieving items

```python title="examples/cache.py"
Cache.get("users:1")
Cache.get("missing", "default")
Cache.get("missing", lambda: expensive_default())

Cache.has("users:1")
Cache.missing("users:1")

Cache.many(["users:1", "users:2"])
Cache.pull("users:1")   # get + forget
```

### Storing items

```python title="examples/cache.py"
Cache.put("users:1", {"name": "Ada"}, 60)
Cache.put_many({"a": 1, "b": 2}, 60)
Cache.forever("config", payload)

Cache.add("users:1", {"name": "Ada"}, 60)  # only if absent (atomic)
Cache.touch("users:1", 120)                # refresh TTL, keep value
```

TTL may be seconds, a `timedelta`, or an aware/naive `datetime`.

### Remembering values

```python title="examples/cache.py"
value = Cache.remember("answer", 60, lambda: expensive())
value = Cache.remember_forever("config", lambda: load_config())
```

`remember` stores the callback result on a miss and returns it on hits.

### The `cache()` helper

```python title="examples/cache.py"
from almasix.cache import cache

cache("users:1")          # get
cache({"k": "v"}, 60)     # put many
repo = cache()            # default store repository
```

### Incrementing / decrementing

```python title="examples/cache.py"
Cache.increment("hits")
Cache.increment("hits", 5)
Cache.decrement("hits")
```

Database `increment` / `decrement` run inside a transaction. `add` is atomic on
every store (process lock / `flock` / `INSERT OR IGNORE`).

### Removing items

```python title="examples/cache.py"
Cache.forget("users:1")
Cache.flush()
```

## Database tables

The database driver ensures two tables on first use:

```sql title="examples/cache.sql"
-- cache
key VARCHAR(255) PRIMARY KEY, value BLOB, expiration INTEGER NULL

-- cache_locks
key VARCHAR(255) PRIMARY KEY, owner VARCHAR(255), expiration INTEGER NOT NULL
```

You can also call `ensure_cache_table()` / `ensure_cache_table_sync()` from
`almasix.cache` in migrations or bootstraps.

## Atomic locks

Locks coordinate work across processes:

```python title="examples/cache.py"
lock = Cache.lock("invoices:settle", seconds=10)
if lock.get():
    try:
        settle()
    finally:
        lock.release()

# Callback form (auto-release)
Cache.lock("deploy").get(lambda: deploy())
Cache.lock("deploy").block(5, lambda: deploy())

with Cache.lock("invoices:settle", seconds=10):
    settle()

# Cross-process release (queue workers, etc.)
owner = lock.owner_token()
Cache.restore_lock("deploy", owner).release()

lock.force_release()   # ignore owner
Cache.flush_locks()
Cache.without_overlapping("report", lambda: build_report())
```

| Store | Lock backend |
| --- | --- |
| array | Atomic `add` under a process lock |
| file | `.locks/` + `fcntl.flock` |
| database | `cache_locks` table |
| redis | `SET NX EX` owner token |

Scheduled `without_overlapping()` prefers cache locks when Cache is booted,
falling back to a filesystem mutex — see [Task Scheduling](/scheduling/).

## Cache tags

Tags let you invalidate related keys as a group. They work on the **array** and
**redis** stores. File and database stores raise `RuntimeError` if you call
`tags()` — Almasix is honest about driver support.

```python title="examples/cache.py"
Cache.tags("users", "authors").put("ada", user, 60)
Cache.tags("users", "authors").get("ada")
Cache.tags("users", "authors").remember("ada", 60, lambda: load())
Cache.tags("users", "authors").forever("ada", user)
Cache.tags("users", "authors").forget("ada")
Cache.tags("users", "authors").flush()
```

## Custom drivers

```python title="examples/cache.py"
from almasix.cache import Cache
from almasix.cache.store import Repository

Cache.extend("mongo", lambda app, cfg, name: Repository(MongoStore(...)))
# then set stores.mongo.driver = "mongo" in config/cache.py
```

## Related

- [Redis](/redis/) — connection manager and drivers
- [Task Scheduling](/scheduling/) — overlap locks
- [Queues](/queues/) — unique jobs / Redis queue
- [File Storage](/filesystem/) — file cache path under `storage/framework/cache`
