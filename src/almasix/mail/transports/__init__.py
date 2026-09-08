"""Mail transports package."""

from __future__ import annotations

from almasix.mail.transports.array import ArrayTransport
from almasix.mail.transports.log import LogTransport
from almasix.mail.transports.smtp import SmtpTransport

__all__ = ["ArrayTransport", "LogTransport", "SmtpTransport"]
