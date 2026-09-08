"""Almasix notifications — Notifiable, channels, database notifications."""

from __future__ import annotations

from almasix.notifications.channels import (
    ArrayChannel,
    BroadcastChannel,
    DatabaseChannel,
    LogChannel,
    MailChannel,
)
from almasix.notifications.helpers import default_notifications_config, notify, notify_now
from almasix.notifications.messages import ResetPasswordNotification, VerifyEmailNotification
from almasix.notifications.notifiable import Notifiable
from almasix.notifications.notification import Notification, ShouldQueue
from almasix.notifications.schema import ensure_tables
from almasix.notifications.verification import (
    MustVerifyEmail,
    hash_email,
    mark_verified_from_request,
    verify_signature,
)

__all__ = [
    "ArrayChannel",
    "BroadcastChannel",
    "DatabaseChannel",
    "LogChannel",
    "MailChannel",
    "MustVerifyEmail",
    "Notifiable",
    "Notification",
    "ResetPasswordNotification",
    "ShouldQueue",
    "VerifyEmailNotification",
    "default_notifications_config",
    "ensure_tables",
    "hash_email",
    "mark_verified_from_request",
    "notify",
    "notify_now",
    "verify_signature",
]
