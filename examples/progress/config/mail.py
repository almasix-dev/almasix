"""Mailers and from address."""

from almasix.config import env

config = {
    "default": env("MAIL_MAILER", "log"),
    "from": {
        "address": env("MAIL_FROM_ADDRESS", "hello@progress.test"),
        "name": env("MAIL_FROM_NAME", "Progress"),
    },
    "mailers": {
        "smtp": {
            "transport": "smtp",
            "host": env("MAIL_HOST", "127.0.0.1"),
            "port": env("MAIL_PORT", 2525),
            "encryption": env("MAIL_ENCRYPTION"),
            "username": env("MAIL_USERNAME"),
            "password": env("MAIL_PASSWORD"),
        },
        "log": {"transport": "log"},
        "array": {"transport": "array"},
    },
}
