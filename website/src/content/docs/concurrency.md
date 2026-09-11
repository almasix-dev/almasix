---
title: Concurrency
description: Run independent tasks at the same time with Concurrency.run across threads, forks, or processes.
---

## Introduction

Sometimes you need several independent, slow things done and none of them
depends on the others. `almasix.concurrency` runs them at the same time and
gives you the results in the shape you asked for.

```python title="examples/concurrency.py"
from almasix.concurrency import Concurrency

user_count, order_count = Concurrency.run([
    lambda: User.query().count(),
    lambda: Order.query().count(),
])
```

The `ConcurrencyServiceProvider` (registered with the foundation) binds a
manager built from `config/concurrency.py`.

## File map

| Piece | Path |
| --- | --- |
| Façade | `src/almasix/concurrency/facade.py` — `Concurrency` |
| Manager | `src/almasix/concurrency/manager.py` — `ConcurrencyManager` |
| Drivers | `src/almasix/concurrency/drivers/` — thread, fork, process, sync |
| Task shapes | `src/almasix/concurrency/tasks.py` — `TaskSet` |
| Deferral | `src/almasix/concurrency/deferred.py` — `DeferredTasks` |
| Provider | `src/almasix/concurrency/provider.py` |
| Exceptions | `src/almasix/concurrency/exceptions.py` |

## How it works

`Concurrency.run()` takes one callable, a list of them, or a mapping, and
returns results in the same shape:

```python title="examples/concurrency.py"
Concurrency.run(lambda: heavy())              # ["result"]

Concurrency.run([first, second])              # ["a", "b"] — in order

Concurrency.run({                             # {"users": 10, "orders": 4}
    "users": lambda: User.query().count(),
    "orders": lambda: Order.query().count(),
})
```

Results come back in the order the tasks were given, not the order they
finished.

### Failures

If a task raises, `run()` re-raises it — but only once every other task has
settled, so nothing is left running in the background:

```python title="examples/concurrency.py"
try:
    Concurrency.run([safe, risky])
except ValueError:
    ...
```

## Drivers

Configure the default in `config/concurrency.py`, or pick one per call:

```python title="examples/concurrency.py"
Concurrency.run(tasks, "fork")
Concurrency.driver("sync").run(tasks)
Concurrency.set_default_driver("fork")
```

| Driver | Parallelism | Accepts | Notes |
| --- | --- | --- | --- |
| `thread` *(default)* | I/O-bound only | any callable | A thread pool; `max_workers` defaults to 16 |
| `fork` | true | any callable | Unix only. Children inherit memory, so closures work; results must be picklable |
| `process` | true | picklable callables | Spawns a fresh interpreter, so tasks must be importable — a module-level function, not a lambda |
| `sync` | none | any callable | Runs in order on the current thread, for debugging |

Almasix defaults to `thread` because Python has real threads and most
concurrency work here is I/O-bound — queries, HTTP calls, file reads — all of
which release the GIL. Reach for `fork` or `process` when the work is
CPU-bound.

`fork` is unsafe to mix with threads in the parent process, which is a
constraint of `fork(2)` rather than of Almasix.

### Custom drivers

```python title="examples/concurrency.py"
Concurrency.extend("my-driver", lambda app, config, name: MyDriver(config))
```

A driver subclasses `Driver` and implements `execute(task_set)`, returning
results in the task order.

## Deferring tasks

When you want the work done but do not need the results:

```python title="examples/concurrency.py"
Concurrency.defer([
    lambda: metrics.record(request),
    lambda: audit.log(request),
])
```

Almasix has no post-response hook yet, so deferred tasks run on a background
thread — and `defer()` returns a `DeferredTasks` handle so tests can `wait()`
for them:

```python title="examples/concurrency.py"
deferred = Concurrency.defer([task])
deferred.finished()
deferred.wait(timeout=5)
```

## Concurrency under ASGI

Almasix runs on ASGI, where the natural way to overlap work is the event loop.
`arun()` awaits coroutines (or plain callables) concurrently on the ASGI
event loop:

```python title="examples/concurrency.py"
async def index():
    users, posts = await Concurrency.arun([
        lambda: fetch_users(),
        lambda: fetch_posts(),
    ])
```

Use `arun()` inside async controllers and `run()` everywhere else. Calling the
blocking `run()` from inside a running event loop would block it.

## Configuration

```python title="config/concurrency.py"
config = {
    "default": env("CONCURRENCY_DRIVER", "thread"),
    "drivers": {
        "thread": {"driver": "thread", "max_workers": 16},
        "fork": {"driver": "fork"},
        "process": {"driver": "process"},
        "sync": {"driver": "sync"},
    },
}
```

A named entry can point at any driver, so `"fast": {"driver": "sync"}` gives
you an alias.

## Design notes

- **`thread` is the default driver**; see above.
- **`arun()`** covers the ASGI / event-loop path.
- **`defer()` runs on a background thread** and returns a waitable handle,
  because Almasix has no post-response deferral hook yet. The same behaviour
  applies to `Batch.defer()` in the HTTP client.
- **The `process` driver rejects unpicklable tasks with a clear error**
  instead of trying to serialize closures — there is no dependency-free
  equivalent of serializable closures in Python.
