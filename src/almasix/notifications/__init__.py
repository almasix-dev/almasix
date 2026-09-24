"""Almasix notifications — Notifiable, channels, database notifications."""

from __future__ import annotations

from almasix.notifications.anonymous import AnonymousNotifiable
from almasix.notifications.channels import (
    ArrayChannel,
    BroadcastChannel,
    DatabaseChannel,
    LogChannel,
    MailChannel,
    SlackChannel,
    VonageChannel,
)
from almasix.notifications.database import (
    DatabaseNotificationStore,
    notifiable_id,
    notifiable_type,
)
from almasix.notifications.events import NotificationSending, NotificationSent
from almasix.notifications.facade import Notification as NotificationFacade
from almasix.notifications.helpers import (
    default_notifications_config,
    default_services_config,
    notify,
    notify_now,
)
from almasix.notifications.mail_message import MailMessage
from almasix.notifications.messages import ResetPasswordNotification, VerifyEmailNotification
from almasix.notifications.messages_builders import SlackMessage, VonageMessage
from almasix.notifications.models import DatabaseNotification
from almasix.notifications.notifiable import Notifiable
from almasix.notifications.notification import HasLocalePreference, Notification, ShouldQueue
from almasix.notifications.schema import ensure_tables
from almasix.notifications.verification import (
    MustVerifyEmail,
    hash_email,
    mark_verified_from_request,
    verify_signature,
)

# Laravel-shaped alias: ``from almasix.notifications.facade import Notification``
Notifications = NotificationFacade

__all__ = [
    "AnonymousNotifiable",
    "ArrayChannel",
    "BroadcastChannel",
    "DatabaseChannel",
    "DatabaseNotification",
    "DatabaseNotificationStore",
    "HasLocalePreference",
    "LogChannel",
    "MailChannel",
    "MailMessage",
    "MustVerifyEmail",
    "Notifiable",
    "Notification",
    "NotificationFacade",
    "NotificationSending",
    "NotificationSent",
    "Notifications",
    "ResetPasswordNotification",
    "ShouldQueue",
    "SlackChannel",
    "SlackMessage",
    "VerifyEmailNotification",
    "VonageChannel",
    "VonageMessage",
    "default_notifications_config",
    "default_services_config",
    "ensure_tables",
    "hash_email",
    "mark_verified_from_request",
    "notifiable_id",
    "notifiable_type",
    "notify",
    "notify_now",
    "verify_signature",
]
