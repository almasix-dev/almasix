"""Redis connections."""

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
