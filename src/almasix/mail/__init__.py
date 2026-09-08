"""Almasix mail — Mailable, Mailer, transports."""

from __future__ import annotations

from almasix.mail.helpers import Mail, mail
from almasix.mail.mailable import (
    Address,
    Attachment,
    Content,
    Envelope,
    Mailable,
    ShouldQueue,
)
from almasix.mail.mailer import Mailer, MailManager, PendingMail
from almasix.mail.message import SentMessage
from almasix.mail.testing import MailAssertions

__all__ = [
    "Address",
    "Attachment",
    "Content",
    "Envelope",
    "Mail",
    "MailAssertions",
    "MailManager",
    "Mailable",
    "Mailer",
    "PendingMail",
    "SentMessage",
    "ShouldQueue",
    "mail",
]
