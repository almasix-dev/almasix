---
title: Mail
description: Mailable classes, Mail façade, log/array/SMTP transports, Markdown mail.
---

## Sending mail

```python
from almasix.mail import Mail, Mailable, Envelope, Content, Attachment

class WelcomeMail(Mailable):
    def envelope(self) -> Envelope:
        return Envelope(subject="Welcome")

    def content(self) -> Content:
        return Content(html="<p>Hello</p>", text="Hello")

    def attachments(self) -> list[Attachment]:
        return [Attachment.from_path("/tmp/guide.pdf")]

Mail.to("ada@example.com").send(WelcomeMail())
Mail.to("ada@example.com").queue(WelcomeMail())  # uses queue when available
```

## Transports

Configure `config/mail.py`:

| Mailer | Transport |
| --- | --- |
| `log` | Writes to the logger (dev default) |
| `array` | In-memory — test assertions |
| `smtp` | Production baseline via smtplib |

```python
from almasix.mail import MailAssertions

MailAssertions(Mail.manager()).assert_sent(WelcomeMail)
```

## Markdown / views

`Content(markdown="mail.welcome", with_data={...})` renders through Prism and
wraps the body in a theme (default `mail.themes.default`, overridable via
`Content.theme`). Place templates under `resources/views/mail/`.

Themeable building blocks ship as Prism components under
`resources/views/components/mail/` — e.g. `<x-mail.button>`, `<x-mail.panel>`,
`<x-mail.subcopy>`.

Plain Markdown bodies (no leading HTML) are converted to HTML components
(headings, bold, button links) before theming.

## Related

- [Notifications](/notifications/)
- [File Storage](/filesystem/) — disk attachments
- [Queues](/queues/)
