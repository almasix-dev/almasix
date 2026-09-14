---
title: Mail
description: Mailable classes, transports (SMTP, ESP, failover), Markdown mail, queueing, and testing.
---

## Introduction

Almasix sends email through class-based **mailables** and a `Mail` façade —
the same shape as Laravel’s Mail docs. Configure transports in `config/mail.py`,
credentials in `config/services.py`, then send or queue.

```python title="examples/mail.py"
from almasix.mail import Mail, Mailable, Envelope, Content

class WelcomeMail(Mailable):
    def envelope(self) -> Envelope:
        return Envelope(subject="Welcome")

    def content(self) -> Content:
        return Content(html="<p>Hello</p>", text="Hello")

Mail.to("ada@example.com").send(WelcomeMail())
```

## Configuration

### Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `MAIL_MAILER` | `log` | Default mailer name |
| `MAIL_FROM_ADDRESS` / `MAIL_FROM_NAME` | example | Global from |
| `MAIL_TO_ADDRESS` | — | Optional always-to (local catch-all) |
| `MAIL_HOST` / `MAIL_PORT` / … | SMTP | SMTP settings |
| `MAILGUN_*` / `POSTMARK_TOKEN` / `RESEND_KEY` / `AWS_*` / `CLOUDFLARE_*` | — | ESP credentials via `config/services.py` |

```python title="config/mail.py"
# default, from, to, mailers: smtp, ses, mailgun, postmark, resend,
# cloudflare, sendmail, log, array, failover, roundrobin
```

### Driver / transport prerequisites

| Transport | Notes |
| --- | --- |
| **log** / **array** | Dev + tests |
| **smtp** | Production baseline (`smtplib`) |
| **mailgun** / **postmark** / **resend** / **ses** / **cloudflare** | HTTP via `almasix.client` |
| **sendmail** | Local binary pipe |
| **failover** | Tries `mailers` in order (`retry_after`) |
| **roundrobin** | Rotates across `mailers` |

### Failover / round robin

```python title="config/mail.py"
"failover": {
    "transport": "failover",
    "mailers": ["postmark", "smtp"],
    "retry_after": 60,
},
"roundrobin": {
    "transport": "roundrobin",
    "mailers": ["ses", "postmark"],
},
```

## Generating mailables

```shell
python smith make:mail OrderShipped
```

Creates a class under `app/mail/` with `envelope` / `content` stubs ready to fill in.

## Writing mailables

A mailable is a class that describes one email. Subclass `Mailable` and implement
the methods you need:

| Method | Role |
| --- | --- |
| `envelope()` | Subject, from, reply-to, tags, metadata, headers |
| `content()` | HTML, text, Markdown view, or Prism view |
| `attachments()` | Files, storage disks, raw bytes, or attachable objects |
| `embeds()` | Inline CID images |
| `with_message(message)` | Last-chance mutate of the built `SentMessage` |

Pass constructor arguments for anything the template needs — the instance is
kept on the built message for assertions and queue serialization metadata.

```python title="app/mail/order_shipped.py"
from almasix.mail import (
    Address,
    Attachment,
    Content,
    EmbeddedImage,
    Envelope,
    Mailable,
)

class OrderShipped(Mailable):
    def __init__(self, order) -> None:
        self.order = order

    def envelope(self) -> Envelope:
        return Envelope(
            subject=f"Order #{self.order.id} shipped",
            from_address=Address("shipping@example.com", "Shipping"),
            reply_to=[Address("support@example.com", "Support")],
            tags=["orders", "fulfillment"],
            metadata={"order_id": self.order.id},
            headers={"X-Order-Id": str(self.order.id)},
        )

    def content(self) -> Content:
        return Content(
            markdown="mail.orders.shipped",
            with_data={
                "order": self.order,
                "tracking_url": self.order.tracking_url,
            },
        )

    def attachments(self) -> list:
        return [
            Attachment.from_path(
                f"storage/invoices/{self.order.id}.pdf",
                name="invoice.pdf",
                mime="application/pdf",
            ),
        ]
```

### Configuring the sender

#### Using the envelope

Set a per-message from address and reply-to on the `Envelope`. Addresses accept
a string, `"Name <addr@example.com>"`, an `Address`, or a `(email, name)` tuple:

```python title="examples/mail.py"
from almasix.mail import Address, Envelope

def envelope(self) -> Envelope:
    return Envelope(
        subject="Welcome aboard",
        from_address=Address("hello@example.com", "Acme"),
        # or: from_address=Address.parse("Acme <hello@example.com>")
        # or: from_address=("hello@example.com", "Acme")
        reply_to=[
            Address("noreply@example.com"),
            "Support <support@example.com>",
        ],
    )
```

#### Using a global from address

When `from_address` is omitted, Almasix uses `config/mail.py`:

```python title="config/mail.py"
"from": {
    "address": env("MAIL_FROM_ADDRESS", "hello@example.com"),
    "name": env("MAIL_FROM_NAME", "Example"),
},
```

### Configuring the view

`Content` chooses how the body is built. You can mix approaches — for example
Markdown for HTML plus an explicit plain-text string.

| Field | Role |
| --- | --- |
| `html` | Raw HTML body |
| `text` | Plain-text body |
| `markdown` | Prism Markdown mail view (theme-wrapped) |
| `view` | Prism HTML view (theme-wrapped when not already a full document) |
| `with_data` | Dict passed into the view as template variables |
| `theme` | Theme layout name (default `mail.themes.default`) |

#### Inline HTML and plain text

```python title="examples/mail.py"
def content(self) -> Content:
    return Content(
        html="<h1>Welcome</h1><p>Thanks for joining.</p>",
        text="Welcome\n\nThanks for joining.",
    )
```

#### Markdown / Prism views

Point `markdown` (or `view`) at a template under `resources/views/`. Dot notation
maps to paths — `mail.orders.shipped` → `resources/views/mail/orders/shipped.prism.html`.

```python title="examples/mail.py"
def content(self) -> Content:
    return Content(
        markdown="mail.orders.shipped",
        with_data={"order": self.order, "app_name": "Acme"},
        theme="mail.themes.default",  # optional override
    )
```

### View data

Everything in `with_data` is available in the Prism template. Public attributes
on the mailable are **not** auto-injected — pass what the view needs explicitly
(or put derived values in `with_data`).

```html title="resources/views/mail/orders/shipped.prism.html"
# Order shipped

Hello **{{ order.customer_name }}**,

Your order **#{{ order.id }}** is on its way.

[Track package]({{ tracking_url }})
```

For a dedicated plain-text twin, ship `mail/orders/shipped.text` (or a
`mail.orders.shipped.text` view). If none exists, Almasix strips HTML tags from
the rendered body.

### Attachments

Return a list from `attachments()`:

```python title="examples/mail.py"
from almasix.mail import Attachment

def attachments(self) -> list[Attachment]:
    return [
        # Absolute or app-relative filesystem path
        Attachment.from_path(
            "/tmp/guide.pdf",
            name="getting-started.pdf",
            mime="application/pdf",
        ),
        # File Storage disk (see File Storage docs)
        Attachment.from_storage(
            "invoices/42.pdf",
            disk="s3",
            name="invoice.pdf",
        ),
        # Raw bytes
        Attachment.from_data(
            self.order.to_csv_bytes(),
            "order.csv",
            mime="text/csv",
        ),
    ]
```

#### Attachable objects

Any object implementing `to_mail_attachment()` → `Attachment` can be listed
directly (Laravel’s `Attachable` pattern):

```python title="app/models/invoice.py"
from almasix.mail import Attachment

class Invoice:
    def to_mail_attachment(self) -> Attachment:
        return Attachment.from_data(
            self.pdf_bytes(),
            f"invoice-{self.id}.pdf",
            mime="application/pdf",
        )
```

```python title="app/mail/order_shipped.py"
def attachments(self) -> list:
    return [self.order.invoice]  # Invoice is Attachable
```

You can also wrap one with `Attachment.from_attachable(obj)`.

### Inline attachments (embeds)

Return `EmbeddedImage` instances from `embeds()` and reference them as
`cid:<content_id>` in HTML:

```python title="examples/mail.py"
from almasix.mail import Content, EmbeddedImage, Envelope, Mailable

class BrandMail(Mailable):
    def content(self) -> Content:
        return Content(
            html='<p><img src="cid:logo" alt="Logo"/></p><p>Hello</p>',
            text="Hello",
        )

    def embeds(self) -> list[EmbeddedImage]:
        return [
            EmbeddedImage(
                content_id="logo",
                data=Path("public/logo.png").read_bytes(),
                mime="image/png",
                name="logo.png",
            ),
        ]
```

### Headers, tags, and metadata

```python title="examples/mail.py"
def envelope(self) -> Envelope:
    return Envelope(
        subject="Receipt",
        headers={
            "X-Custom-Header": "value",
            "List-Unsubscribe": "<mailto:unsub@example.com>",
        },
        tags=["transactions", "receipts"],
        metadata={
            "user_id": self.user.id,
            "campaign": "onboarding",
        },
    )
```

Tags and metadata travel on the `SentMessage` for assertions and ESP drivers
(Mailgun `o:tag` / `v:*`, Postmark `Tag` / `Metadata`, SES message tags).

### Customizing the built message

Override `with_message` to adjust the rendered `SentMessage` immediately before
the transport sends it (Laravel’s `withSymfonyMessage` equivalent):

```python title="examples/mail.py"
def with_message(self, message) -> None:
    message.headers["X-Mailer"] = "Almasix"
    if message.html:
        message.html = message.html.replace("{{YEAR}}", "2026")
```

## Markdown mailables

Markdown mailables keep the body in a Prism template and wrap it in a themeable
HTML layout — the same workflow as Laravel’s Markdown mail.

### Writing Markdown messages

```python title="app/mail/welcome_mail.py"
def content(self) -> Content:
    return Content(
        markdown="mail.welcome",
        with_data={"name": self.user.name, "board_url": "/progress"},
    )
```

```html title="resources/views/mail/welcome.prism.html"
# Welcome

Hello **{{ name }}**,

Thanks for joining {{ app_name or "Acme" }}.

[Open the board]({{ board_url }})

<x-mail.panel>
Need help? Just reply to this email.
</x-mail.panel>

<x-mail.subcopy>
If the button-style link above does not work, copy and paste this URL into
your browser: {{ board_url }}
</x-mail.subcopy>
```

Plain Markdown (no leading HTML) is converted to HTML before theming: `#`
headings, `**bold**`, paragraphs, and `[Label](url)` lines become styled button
links. You can also drop in mail components anywhere in the body.

#### Button component

```html title="resources/views/mail/orders/shipped.prism.html"
<x-mail.button url="{{ tracking_url }}">
Track package
</x-mail.button>
```

Props: `url` (required), optional `color` (passed through to the component).

#### Panel component

```html title="resources/views/mail/orders/shipped.prism.html"
<x-mail.panel>
This shipment includes fragile items — open carefully.
</x-mail.panel>
```

#### Subcopy component

Small print under the main card content (footer-style notes, raw URLs):

```html title="resources/views/mail/welcome.prism.html"
<x-mail.subcopy>
If you’re having trouble clicking the button, copy this URL:
{{ url }}
</x-mail.subcopy>
```

### Customizing the theme

The default theme is `mail.themes.default`
(`resources/views/mail/themes/default.prism.html`). It receives `slot` (the
rendered body), plus `app_name`, `subject`, and `footer`. Override per message
with `Content(..., theme="mail.themes.brand")`, or edit the default theme file.
If no theme view is present, a built-in HTML layout is used.

## Sending mail

```python title="examples/mail.py"
from almasix.mail import Mail, mail

Mail.to("ada@example.com").send(WelcomeMail())
Mail.to("ada@example.com").cc("cc@example.com").bcc("audit@example.com").send(WelcomeMail())

Mail.mailer("smtp").to("ada@example.com").send(WelcomeMail())
mail("postmark").to("ada@example.com").send(WelcomeMail())

# Pin a mailer on the mailable itself
Mail.send(WelcomeMail().mailer("ses"))
```

Loop recipients by calling `to(...).send(...)` per address, or pass several
addresses into one `to(...)`.

### Queueing mail

```python title="examples/mail.py"
from almasix.mail import Mailable, ShouldQueue, Mail
from datetime import timedelta

class WelcomeMail(ShouldQueue, Mailable):
    ...

Mail.to("ada@example.com").send(WelcomeMail())          # queues because ShouldQueue
Mail.to("ada@example.com").queue(WelcomeMail())         # always attempt to queue
Mail.later(60, WelcomeMail())                           # delay in seconds
Mail.later(timedelta(minutes=5), WelcomeMail())
WelcomeMail().on_queue("emails").on_connection("redis")
```

Queued delivery uses `SendQueuedMailable`. If no queue is available, `queue()` /
`later()` fall back to synchronous send. The **array** transport records queued
messages separately for assertions.

## Rendering / preview

```python title="examples/mail.py"
html = OrderShipped(order).render()
```

Return that string from a route to preview the mailable in the browser without
sending.

## Localizing mailables

```python title="examples/mail.py"
OrderShipped(order).set_locale("sw")
```

The locale is applied for the duration of render/send, then restored. Notifiables
that implement `preferred_locale()` / `HasLocalePreference` set the locale
automatically when the message is sent as a notification.

## Testing

```python title="tests/feature/mail_test.py"
from almasix.mail import Mail

mail = Mail.fake()
Mail.to("ada@example.com").send(OrderShipped(order))

mail.assert_sent(OrderShipped)
mail.assert_sent(
    OrderShipped,
    lambda m: m.to[0].address == "ada@example.com" and m.subject.startswith("Order"),
)
mail.assert_not_sent(WelcomeMail)
mail.assert_queued(WelcomeMail)
mail.assert_nothing_sent()
```

See also [Mocking](/testing/mocking/) (`fake("mail")`).

## Mail and local development

Prefer `MAIL_MAILER=log` or Mailpit over real SMTP while iterating. Set
`MAIL_TO_ADDRESS` (config `mail.to`) to force every message to a catch-all
inbox — CC/BCC are cleared when always-to is active.

## Events

Listen for `MessageSending` (return `False` to abort) and `MessageSent` via
`almasix.events`.

```python title="app/providers/app_service_provider.py"
from almasix.events import listen
from almasix.mail import MessageSending, MessageSent

listen(MessageSending, lambda e: print(e.message.subject))
listen(MessageSent, lambda e: metrics.increment("mail.sent"))
```

## Related

- [Notifications](/notifications/) — mail as a notification channel / `MailMessage`
- [File Storage](/filesystem/) — disk attachments
- [Queues](/queues/)
- [Localization](/localization/)
- [Mocking](/testing/mocking/)
