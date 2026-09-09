"""Queue connections."""

from almasix.config import env

config = {
    "default": env("QUEUE_CONNECTION", "sync"),
    "connections": {
        "sync": {"driver": "sync"},
        "database": {
            "driver": "database",
            "table": "jobs",
            "queue": "default",
            "retry_after": 90,
        },
        "redis": {
            "driver": "redis",
            "connection": env("REDIS_QUEUE_CONNECTION", "default"),
            "queue": "queues",
        },
    },
    "failed": {
        "driver": "database",
        "connection": env("DB_CONNECTION", "sqlite"),
        "table": "failed_jobs",
    },
}
