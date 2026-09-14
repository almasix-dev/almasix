"""Mail transports package."""

from __future__ import annotations

from almasix.mail.transports.array import ArrayTransport
from almasix.mail.transports.cloudflare import CloudflareTransport
from almasix.mail.transports.composite import FailoverTransport, RoundRobinTransport
from almasix.mail.transports.log import LogTransport
from almasix.mail.transports.mailgun import MailgunTransport
from almasix.mail.transports.postmark import PostmarkTransport
from almasix.mail.transports.resend import ResendTransport
from almasix.mail.transports.sendmail import SendmailTransport
from almasix.mail.transports.ses import SesTransport
from almasix.mail.transports.smtp import SmtpTransport

__all__ = [
    "ArrayTransport",
    "CloudflareTransport",
    "FailoverTransport",
    "LogTransport",
    "MailgunTransport",
    "PostmarkTransport",
    "ResendTransport",
    "RoundRobinTransport",
    "SendmailTransport",
    "SesTransport",
    "SmtpTransport",
]
