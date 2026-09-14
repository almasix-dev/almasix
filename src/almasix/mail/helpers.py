"""``mail()`` helper and default mail config."""

from __future__ import annotations

from typing import Any

from almasix.mail.mailable import Address, Mailable
from almasix.mail.mailer import Mail, Mailer, MailManager, PendingMail


def mail(name: str | None = None) -> Mailer:
    """Resolve a mailer (default mailer when ``name`` is omitted)."""
    return Mail.mailer(name)


def default_mail_config() -> dict[str, Any]:
    """Default ``config/mail.py`` shape."""
    return {
        "default": "log",
        "from": {
            "address": "hello@example.com",
            "name": "Example",
        },
        "to": None,  # local-dev always-to: {"address": "...", "name": "..."}
        "mailers": {
            "smtp": {
                "transport": "smtp",
                "host": "127.0.0.1",
                "port": 2525,
                "encryption": None,
                "username": None,
                "password": None,
                "timeout": None,
                "local_domain": None,
            },
            "ses": {"transport": "ses"},
            "mailgun": {"transport": "mailgun"},
            "postmark": {"transport": "postmark"},
            "resend": {"transport": "resend"},
            "cloudflare": {"transport": "cloudflare"},
            "sendmail": {
                "transport": "sendmail",
                "path": "/usr/sbin/sendmail -t -i",
            },
            "log": {
                "transport": "log",
                "channel": None,
            },
            "array": {
                "transport": "array",
            },
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


__all__ = [
    "Address",
    "Mail",
    "MailManager",
    "Mailable",
    "Mailer",
    "PendingMail",
    "default_mail_config",
    "mail",
]
