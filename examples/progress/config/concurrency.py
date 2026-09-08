"""Concurrency drivers."""

from almasix.config import env

config = {
    # "thread" runs any callable and suits I/O-bound work; "fork" gives real
    # parallelism on Unix; "process" needs picklable tasks; "sync" is serial.
    "default": env("CONCURRENCY_DRIVER", "thread"),
    "drivers": {
        "thread": {
            "driver": "thread",
            "max_workers": int(env("CONCURRENCY_MAX_WORKERS", 16) or 16),
        },
        "fork": {"driver": "fork"},
        "process": {"driver": "process"},
        "sync": {"driver": "sync"},
    },
}
