"""Mailers and from address."""

from almasix.config import env

_mail_to = env("MAIL_TO_ADDRESS")

config = {
    "default": env("MAIL_MAILER", "log"),
    "from": {
        "address": env("MAIL_FROM_ADDRESS", "hello@example.com"),
        "name": env("MAIL_FROM_NAME", "Example"),
    },
    "to": {"address": _mail_to, "name": env("MAIL_TO_NAME")} if _mail_to else None,
    "mailers": {
        "smtp": {
            "transport": "smtp",
            "host": env("MAIL_HOST", "127.0.0.1"),
            "port": env("MAIL_PORT", 2525),
            "encryption": env("MAIL_ENCRYPTION"),
            "username": env("MAIL_USERNAME"),
            "password": env("MAIL_PASSWORD"),
        },
        "ses": {"transport": "ses"},
        "mailgun": {"transport": "mailgun"},
        "postmark": {"transport": "postmark"},
        "resend": {"transport": "resend"},
        "cloudflare": {"transport": "cloudflare"},
        "sendmail": {
            "transport": "sendmail",
            "path": env("MAIL_SENDMAIL_PATH", "/usr/sbin/sendmail -t -i"),
        },
        "log": {"transport": "log"},
        "array": {"transport": "array"},
        "failover": {
            "transport": "failover",
            "mailers": ["smtp", "log"],
            "retry_after": 60,
        },
        "roundrobin": {
            "transport": "roundrobin",
            "mailers": ["smtp", "log"],
        },
    },
}
