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
            "log": {
                "transport": "log",
                "channel": None,
            },
            "array": {
                "transport": "array",
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
