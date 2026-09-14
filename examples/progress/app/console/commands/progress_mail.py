"""Demo M57 mail + notifications exhaust."""

from __future__ import annotations

import asyncio

from almasix.client import Http
from almasix.console.command import Command
from almasix.mail import Content, Envelope, Mail, Mailable
from almasix.mail.mailer import MailManager
from almasix.notifications import MailMessage, Notifiable, Notification, notify_now
from almasix.notifications.facade import Notification as NotificationFacade
from almasix.notifications.messages_builders import SlackMessage, VonageMessage


class _DemoUser(Notifiable):
    def __init__(self) -> None:
        self.email = "ada@progress.test"
        self.id = 1
        self.phone = "+15551212"

    def get_key(self) -> int:
        return self.id

    def preferred_locale(self) -> str:
        return "en"

    def route_notification_for_vonage(self) -> str:
        return self.phone

    def route_notification_for_slack(self) -> str:
        return "#progress"


class InvoicePaid(Notification):
    def via(self, notifiable):
        return ["mail", "array"]

    def to_mail(self, notifiable):
        return (
            MailMessage()
            .subject("Invoice paid")
            .greeting("Hello!")
            .line("Your invoice was paid.")
            .action("View", "https://example.test/invoices/1")
        )

    def to_array(self, notifiable):
        return {"ok": True}


class SmsAlert(Notification):
    def via(self, notifiable):
        return ["vonage"]

    def to_vonage(self, notifiable):
        return VonageMessage().content("Progress demo SMS")


class SlackAlert(Notification):
    def via(self, notifiable):
        return ["slack"]

    def to_slack(self, notifiable):
        return SlackMessage().content("Progress demo Slack").header_block("M57")


class WelcomeMail(Mailable):
    def envelope(self) -> Envelope:
        return Envelope(subject="M57 welcome", tags=["progress"])

    def content(self) -> Content:
        return Content(html="<p>Hello from M57</p>", text="Hello from M57")


class ProgressMailCommand(Command):
    signature = "progress:mail"
    description = "Demo M57 mail + notifications exhaust (ESP fakes, on-demand, Slack/Vonage)"

    def handle(self) -> int:
        manager = MailManager(
            config={
                "default": "failover",
                "from": {"address": "hello@progress.test", "name": "Progress"},
                "mailers": {
                    "log": {"transport": "log"},
                    "array": {"transport": "array"},
                    "failover": {
                        "transport": "failover",
                        "mailers": ["array", "log"],
                        "retry_after": 60,
                    },
                },
            }
        )
        Mail.set_manager(manager)
        Mail.mailer("failover").to("ada@progress.test").send(WelcomeMail())
        self.info("failover → array")

        Http.fake(lambda req: Http.response({"id": "mg_1"}, 200))
        manager.set_config(
            {
                "default": "mailgun",
                "from": {"address": "hello@progress.test", "name": "Progress"},
                "mailers": {
                    "mailgun": {"transport": "mailgun", "domain": "mg.test", "secret": "key"},
                    "array": {"transport": "array"},
                },
            }
        )
        Mail.set_manager(manager)
        Mail.mailer("mailgun").to("ada@progress.test").send(WelcomeMail())
        self.info("mailgun → http fake")

        rendered = WelcomeMail().render()
        self.info(f"render → {rendered[:20]}…")

        manager.set_config(
            {
                "default": "array",
                "from": {"address": "hello@progress.test", "name": "Progress"},
                "mailers": {"array": {"transport": "array"}, "log": {"transport": "log"}},
            }
        )
        Mail.set_manager(manager)

        user = _DemoUser()
        asyncio.run(notify_now(user, InvoicePaid()))
        self.info("mail message → sent")

        asyncio.run(
            NotificationFacade.route("mail", "ondemand@progress.test").notify(InvoicePaid())
        )
        self.info("on-demand → routed")

        Http.fake(lambda req: Http.response({"messages": [{"status": "0"}]}, 200))
        asyncio.run(notify_now(user, SmsAlert()))
        self.info("vonage → http fake")

        Http.fake(lambda req: Http.response({"ok": True}, 200))
        asyncio.run(notify_now(user, SlackAlert()))
        self.info("slack → http fake")

        self.success("mail demo ok")
        return 0
