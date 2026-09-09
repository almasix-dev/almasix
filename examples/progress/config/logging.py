"""Logging channels.

App code: ``from almasix.log import Log`` then ``Log.info(...)``.
"""

from almasix.config import env

config = {
    "default": env("LOG_CHANNEL", "stack"),
    "channels": {
        "stack": {
            "driver": "stack",
            "channels": ["single"],
            "ignore_exceptions": False,
        },
        "single": {
            "driver": "single",
            "path": "storage/logs/almasix.log",
            "level": env("LOG_LEVEL", "debug"),
        },
        "daily": {
            "driver": "daily",
            "path": "storage/logs/almasix.log",
            "level": env("LOG_LEVEL", "debug"),
            "days": 14,
        },
        "stderr": {
            "driver": "stderr",
            "level": env("LOG_LEVEL", "debug"),
        },
        "null": {
            "driver": "null",
        },
    },
}
