---
title: Notifications
description: Notifiable models, mail/database/broadcast/Slack/Vonage channels, on-demand routing, and testing.
---

## Introduction

Notifications deliver short messages over one or more **channels**: mail,
database, broadcast, Vonage (SMS), Slack, log, and array (tests).

```python title="examples/notifications.py"
from almasix.notifications import Notifiable, Notification, notify

class InvoicePaid(Notification):
    def via(self, notifiable):
        return ["mail", "database"]

    def to_mail(self, notifiable):
        from almasix.notifications import MailMessage
        return MailMessage().subject("Paid").line("Thanks!")

await user.notify(InvoicePaid())
```

## Generating notifications

```shell
python smith make:notification InvoicePaid
```

Creates a class under `app/notifications/` with `via` and channel stubs.

## Sending notifications

### Notifiable

```python title="app/models/user.py"
from almasix.auth import AuthenticatableMixin
from almasix.notifications import Notifiable
from almasix.orm import Model

class User(AuthenticatableMixin, Notifiable, Model):
    ...

await user.notify(InvoicePaid())
await user.notify_now(InvoicePaid(), channels=["mail"])
```

### Notification façade

```python title="examples/notifications.py"
from almasix.notifications.facade import Notification

Notification.send(users, InvoicePaid())
Notification.send_now(users, InvoicePaid())
Notification.locale("sw").send(users, InvoicePaid())
```

### On-demand notifications

Route without a persisted model:

```python title="examples/notifications.py"
Notification.route("mail", "guest@example.com").notify(InvoicePaid())
Notification.route("vonage", "+15551212").route("slack", "#ops").notify(Alert())
```

### Specifying delivery channels

Every notification implements `via(notifiable)` and returns channel names — or
channel **classes** for custom drivers:

```python title="app/notifications/invoice_paid.py"
def via(self, notifiable):
    if notifiable.prefers_sms:
        return ["vonage"]
    return ["mail", "database", "broadcast"]
```

| Channel | Builder method | Returns |
| --- | --- | --- |
| **mail** | `to_mail` | `MailMessage`, `Mailable`, or dict |
| **database** | `to_database` | JSON-serializable dict |
| **broadcast** | `to_broadcast` (optional) | dict (falls back to `to_array`) |
| **vonage** | `to_vonage` | `VonageMessage` or dict |
| **slack** | `to_slack` | `SlackMessage` or dict |
| **log** / **array** | `to_array` | dict (defaults to `to_database`) |

Configure drivers in `config/notifications.py`. Credentials live in
`config/services.py`.

### Queueing notifications

```python title="app/notifications/invoice_paid.py"
from almasix.notifications import Notification, ShouldQueue

class InvoicePaid(ShouldQueue, Notification):
    queue = "notifications"   # or True for the default queue
    connection = "redis"
    delay = 30                # seconds

    def via_queues(self) -> dict[str, str]:
        return {"mail": "mail", "database": "default"}
```

Use `notify_now` / `user.notify_now(...)` to force synchronous delivery.

### Routing notifications

By default the mail channel uses `notifiable.email`. Override per channel:

```python title="app/models/user.py"
class User(Notifiable, Model):
    def route_notification_for_mail(self) -> str:
        return self.billing_email

    def route_notification_for_vonage(self) -> str:
        return self.phone_number

    def route_notification_for_slack(self) -> str:
        return "#billing"
        # or an incoming webhook URL: "https://hooks.slack.com/services/..."

    def route_notification_for_broadcast(self):
        return f"App.Models.User.{self.id}"
```

Or implement `route_notification_for(channel, notification)` for full control.

## Mail notifications

When `"mail"` is in `via`, implement `to_mail`. Prefer the fluent
`MailMessage` builder for transactional copy; return a full `Mailable` when you
need Markdown themes, custom Prism layouts, or rich attachments.

### Formatting mail messages

```python title="app/notifications/invoice_paid.py"
from almasix.notifications import MailMessage, Notification

class InvoicePaid(Notification):
    def __init__(self, invoice) -> None:
        self.invoice = invoice

    def via(self, notifiable):
        return ["mail"]

    def to_mail(self, notifiable):
        url = f"https://example.com/invoices/{self.invoice.id}"
        return (
            MailMessage()
            .subject(f"Invoice #{self.invoice.id} paid")
            .greeting(f"Hello {notifiable.name}!")
            .line("Your recent invoice has been paid successfully.")
            .line(f"Amount: {self.invoice.total}")
            .action("View invoice", url)
            .line("Thank you for your business.")
        )
```

`MailMessage` builds a small HTML + text body and sends it through the mailer.
Lines before `action(...)` are intro lines; lines after become outro lines.

#### Error / success level

```python title="examples/notifications.py"
MailMessage().error().subject("Payment failed").line("Please update your card.")
MailMessage().success().subject("You're verified").line("Your email is confirmed.")
```

`level` is stored on the message (`info` by default, or `success` / `error`) for
theming and future presentation hooks.

#### Sender, reply-to, and mailer

```python title="examples/notifications.py"
(
    MailMessage()
    .from_("billing@example.com", "Billing")
    .reply_to("support@example.com")
    .mailer("postmark")
    .subject("Receipt")
    .line("Here is your receipt.")
)
```

#### Attachments on MailMessage

```python title="examples/notifications.py"
(
    MailMessage()
    .subject("Your export")
    .line("The export you requested is attached.")
    .attach("storage/exports/report.csv", name="report.csv", mime="text/csv")
    .attach_data(b"%PDF...", "summary.pdf", mime="application/pdf")
)
```

#### Tags and metadata

```python title="examples/notifications.py"
(
    MailMessage()
    .subject("Receipt")
    .line("Thanks!")
    .tag("transactions")
    .metadata("invoice_id", self.invoice.id)
)
```

These flow onto the underlying mailable envelope for ESP drivers.

### Other mail formatting options

A plain dict is accepted for quick payloads (no fluent builder):

```python title="examples/notifications.py"
def to_mail(self, notifiable):
    return {
        "subject": "Invoice paid",
        "text": "Thanks for your payment.",
        "html": "<p>Thanks for your payment.</p>",
    }
```

### Using mailables

For Markdown themes, Prism layouts, embeds, or attachable objects, return a
`Mailable` from `to_mail` — everything on the [Mail](/mail/#writing-mailables)
page applies:

```python title="app/notifications/invoice_paid.py"
from almasix.mail import Content, Envelope, Mailable

def to_mail(self, notifiable):
    invoice = self.invoice

    class PaidMail(Mailable):
        def envelope(self) -> Envelope:
            return Envelope(subject=f"Invoice #{invoice.id} paid")

        def content(self) -> Content:
            return Content(
                markdown="mail.invoice.paid",
                with_data={"invoice": invoice, "user": notifiable},
            )

    return PaidMail()
```

```html title="resources/views/mail/invoice/paid.prism.html"
# Invoice paid

Hi **{{ user.name }}**,

Invoice **#{{ invoice.id }}** for **{{ invoice.total }}** is settled.

<x-mail.button url="{{ invoice.url }}">
View invoice
</x-mail.button>

<x-mail.subcopy>
Questions? Reply to this email.
</x-mail.subcopy>
```

See [Markdown mailables](/mail/#markdown-mailables) for buttons, panels,
subcopy, and themes.

## Markdown mail notifications

There is no separate generator — use a Markdown `Mailable` from `to_mail` as
above, or keep using `MailMessage` for simple transactional lines. Both go
through the same mailer and transports.

## Database notifications

### Prerequisites

```shell
python smith notifications:table
python smith migrate
```

```python title="examples/notifications.py"
from almasix.notifications import ensure_tables

await ensure_tables()
```

Schema: UUID `id`, `type`, `notifiable_type` / `notifiable_id`, JSON `data`,
nullable `read_at`, timestamps.

### Formatting database notifications

```python title="app/notifications/invoice_paid.py"
def to_database(self, notifiable):
    return {
        "invoice_id": self.invoice.id,
        "amount": str(self.invoice.total),
        "message": f"Invoice #{self.invoice.id} was paid",
    }
```

`to_array` defaults to `to_database` and feeds the log / array channels.

### Accessing notifications

```python title="examples/notifications.py"
unread = await user.unread_notifications()
all_rows = await user.notifications()
await user.mark_notification_as_read(unread[0]["id"])
```

Each row includes `id`, `type`, `data`, `read_at`, and timestamps.

## Broadcast notifications

Include `"broadcast"` in `via`. Optionally implement `to_broadcast`; otherwise
the channel uses `to_array`. The event name defaults to
`BroadcastNotificationCreated`. Override with `broadcast_as`:

```python title="examples/notifications.py"
class InvoicePaid(Notification):
    def via(self, notifiable):
        return ["database", "broadcast"]

    def to_broadcast(self, notifiable):
        return {
            "invoice_id": self.invoice.id,
            "amount": str(self.invoice.total),
        }

    def broadcast_as(self) -> str:
        return "invoice.paid"
```

See [Broadcasting](/broadcasting/) for private channels and client auth.

## SMS notifications (Vonage)

```python title="app/notifications/login_code.py"
from almasix.notifications import Notification, VonageMessage

class LoginCode(Notification):
    def __init__(self, code: str) -> None:
        self.code = code

    def via(self, notifiable):
        return ["vonage"]

    def to_vonage(self, notifiable):
        return (
            VonageMessage()
            .content(f"Your login code is {self.code}")
            .from_("Acme")           # overrides VONAGE_SMS_FROM when set
            .unicode_()              # enable unicode if needed
            .client_reference_(str(notifiable.id))
        )
```

Routing: `route_notification_for_vonage()` (or `route_notification_for("sms")`).

Env / `config/services.py`: `VONAGE_KEY`, `VONAGE_SECRET`, `VONAGE_SMS_FROM`.

## Slack notifications

```python title="app/notifications/deploy_finished.py"
from almasix.notifications import Notification, SlackMessage

class DeployFinished(Notification):
    def __init__(self, version: str) -> None:
        self.version = version

    def via(self, notifiable):
        return ["slack"]

    def to_slack(self, notifiable):
        return (
            SlackMessage()
            .content(f"Deployed {self.version}")
            .header_block("Production deploy")
            .section_block(f"*Version:* `{self.version}`\n*By:* {notifiable.name}")
            .to("#deploys")
        )
```

- `content` — fallback text
- `header_block` / `section_block` — Block Kit payloads
- `to(channel)` — channel override on the message

Routing: `route_notification_for_slack()` may return a channel name (`#ops`) or
an incoming webhook URL (`https://hooks.slack.com/...`).

Env: `SLACK_BOT_USER_OAUTH_TOKEN`, `SLACK_BOT_USER_DEFAULT_CHANNEL`.

## Localizing notifications

```python title="examples/notifications.py"
await user.notify(InvoicePaid(invoice).set_locale("sw"))
Notification.locale("sw").send(users, InvoicePaid(invoice))
```

Implement `preferred_locale()` / mix in `HasLocalePreference` so the user’s
stored locale is applied automatically (including when the notification is
queued):

```python title="app/models/user.py"
from almasix.notifications import HasLocalePreference, Notifiable

class User(Notifiable, HasLocalePreference, Model):
    def preferred_locale(self) -> str:
        return self.locale or "en"
```

## Testing

```python title="tests/feature/notifications_test.py"
from almasix.notifications.facade import Notification

fake = Notification.fake()
await user.notify(InvoicePaid(invoice))

fake.assert_sent_to(user, InvoicePaid)
fake.assert_sent_on_channel(InvoicePaid, "mail")
fake.assert_sent_times(InvoicePaid, 1)
fake.assert_not_sent_to(other, InvoicePaid)
```

Callbacks may take the notification, or the notification and the notifiable:

```python title="examples/notifications.py"
fake.assert_sent_to(
    user,
    InvoicePaid,
    lambda n, to: n.invoice.id == 42 and to.get_key() == 1,
)
```

See [Mocking](/testing/mocking/).

## Notification events

`NotificationSending` (return `False` to skip that channel) and
`NotificationSent` via `almasix.events`.

```python title="app/providers/app_service_provider.py"
from almasix.events import listen
from almasix.notifications import NotificationSending, NotificationSent

listen(NotificationSending, lambda e: e.channel != "log")
listen(NotificationSent, lambda e: audit(e.notification, e.channel))
```

## Custom channels

```python title="app/notifications/channels/voice.py"
class VoiceChannel:
    name = "voice"

    async def send(self, notifiable, notification):
        message = notification.to_voice(notifiable)
        await dialer.say(notifiable.phone, message)
        return message
```

```python title="app/notifications/alert.py"
class Alert(Notification):
    def via(self, notifiable):
        return [VoiceChannel]

    def to_voice(self, notifiable):
        return "Server CPU above 90 percent"
```

## Password reset and email verification

`ResetPasswordNotification`, `MustVerifyEmail`, signed verification URLs, and
the `verified` middleware — see [Passwords](/passwords/) and
[Authentication](/authentication/).

## Related

- [Mail](/mail/) — writing mailables, Markdown themes, attachments
- [Broadcasting](/broadcasting/)
- [Queues](/queues/)
- [Localization](/localization/)
- [Mocking](/testing/mocking/)
