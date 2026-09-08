---
title: Notifications
description: Notifiable models, channels, database notifications, and email verification.
---

## Notifiable

```python
from almasix.notifications import Notifiable, Notification, notify

class InvoicePaid(Notification):
    def via(self, notifiable):
        return ["mail", "database"]

    def to_mail(self, notifiable):
        return {"subject": "Paid", "text": "Thanks!"}

    def to_database(self, notifiable):
        return {"invoice_id": 42}

await user.notify(InvoicePaid())
await notify(user, InvoicePaid())
await user.notify_now(InvoicePaid(), channels=["mail"])
```

Channels: **mail**, **database** (`notifications` table via `ensure_tables()`),
**broadcast**, **log**, **array** (tests).

The broadcast channel sends the notification to the notifiable's own private
channel, so it arrives in an open browser as it is stored:

```python
class InvoicePaid(Notification):
    def via(self, notifiable):
        return ["database", "broadcast"]

    def to_broadcast(self, notifiable):
        return {"invoice_id": 42}
```

See [Broadcasting](/broadcasting/) for the channel, the socket, and how a
client authorizes itself.

## Password reset + verification

`NotificationServiceProvider` wires the password broker to `ResetPasswordNotification` (mail) by default.

```python
from almasix.notifications import MustVerifyEmail, Notifiable

class User(AuthenticatableMixin, Notifiable, MustVerifyEmail, Model):
    ...

url = user.verification_url()  # signed HMAC link
await user.send_email_verification_notification()
```

Progress ships `/email/verify`, `/email/verify/{id}/{hash}`, and the `verified` middleware on protected routes.

## Related

- [Mail](/mail/)
- [Broadcasting](/broadcasting/)
- [Passwords](/passwords/)
- [Authentication](/authentication/)
- [Queues](/queues/)
