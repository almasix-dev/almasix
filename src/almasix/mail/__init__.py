"""Almasix mail — Mailable, Mailer, transports."""

from __future__ import annotations

from almasix.mail.events import MessageSending, MessageSent
from almasix.mail.helpers import Mail, mail
from almasix.mail.mailable import (
    Address,
    Attachable,
    Attachment,
    Content,
    EmbeddedImage,
    Envelope,
    Mailable,
    ShouldQueue,
)
from almasix.mail.mailer import Mailer, MailManager, PendingMail
from almasix.mail.message import SentMessage
from almasix.mail.testing import MailAssertions

__all__ = [
    "Address",
    "Attachable",
    "Attachment",
    "Content",
    "EmbeddedImage",
    "Envelope",
    "Mail",
    "MailAssertions",
    "MailManager",
    "Mailable",
    "Mailer",
    "MessageSending",
    "MessageSent",
    "PendingMail",
    "SentMessage",
    "ShouldQueue",
    "mail",
]
