"""M57 — Mail + Notifications exhaust unit tests."""

from __future__ import annotations

import pytest

from almasix.client import Http
from almasix.events import listen
from almasix.mail import Content, Envelope, Mail, Mailable, MessageSending
from almasix.mail.mailable import Attachment, EmbeddedImage
from almasix.mail.mailer import MailManager
from almasix.notifications import (
    HasLocalePreference,
    MailMessage,
    Notifiable,
    Notification,
    notify_now,
)
from almasix.notifications.facade import Notification as NotificationFacade
from almasix.notifications.messages_builders import SlackMessage, VonageMessage


class Welcome(Mailable):
    def envelope(self) -> Envelope:
        return Envelope(subject="Hi", tags=["t"], metadata={"k": "v"}, headers={"X-Test": "1"})

    def content(self) -> Content:
        return Content(html="<p>Hi</p>", text="Hi")

    def embeds(self) -> list[EmbeddedImage]:
        return [EmbeddedImage(content_id="logo", data=b"PNG", mime="image/png")]


class User(Notifiable, HasLocalePreference):
    def __init__(self) -> None:
        self.email = "ada@test"
        self.id = 7
        self.locale = "sw"

    def get_key(self) -> int:
        return self.id

    def preferred_locale(self) -> str:
        return self.locale

    def route_notification_for_vonage(self) -> str:
        return "+1"

    def route_notification_for_slack(self) -> str:
        return "#general"


class Paid(Notification):
    def via(self, notifiable):
        return ["mail", "array"]

    def to_mail(self, notifiable):
        return MailMessage().subject("Paid").line("Thanks").action("Go", "https://x.test")

    def to_array(self, notifiable):
        return {"paid": True}


class CustomChannel:
    name = "custom"
    sent: list = []

    async def send(self, notifiable, notification):
        CustomChannel.sent.append((notifiable, notification))
        return "ok"


class CustomNote(Notification):
    def via(self, notifiable):
        return [CustomChannel]


def _array_manager(**extra) -> MailManager:
    cfg = {
        "default": "array",
        "from": {"address": "from@test", "name": "T"},
        "mailers": {"array": {"transport": "array"}, "log": {"transport": "log"}},
        **extra,
    }
    manager = MailManager(config=cfg)
    Mail.set_manager(manager)
    return manager


def test_mailable_render_and_later_and_failover() -> None:
    assert "Hi" in Welcome().render()
    manager = _array_manager(
        mailers={
            "array": {"transport": "array"},
            "log": {"transport": "log"},
            "failover": {"transport": "failover", "mailers": ["array", "log"]},
            "roundrobin": {"transport": "roundrobin", "mailers": ["array", "log"]},
        }
    )
    Mail.set_manager(manager)
    Mail.mailer("failover").to("a@b.c").send(Welcome())
    Mail.mailer("roundrobin").to("a@b.c").send(Welcome())
    Mail.later(0, Welcome())
    transport = manager.array_transport()
    assert transport is not None
    assert len(transport.sent_messages) + len(transport.queued_messages) >= 2


def test_mail_events_can_abort() -> None:
    from almasix.events import Event

    _array_manager()
    Event.flush()
    listen(MessageSending, lambda e: False)
    result = Mail.to("a@b.c").send(Welcome())
    assert result is None
    Event.flush()


def test_mailgun_and_postmark_with_http_fake() -> None:
    from almasix.client.facade import set_factory
    from almasix.client.factory import Factory

    set_factory(Factory())
    Http.fake(lambda req: Http.response({"ok": True}, 200))
    manager = MailManager(
        config={
            "default": "mailgun",
            "from": {"address": "from@test"},
            "mailers": {
                "mailgun": {"transport": "mailgun", "domain": "mg.test", "secret": "s"},
                "postmark": {"transport": "postmark", "token": "tok"},
                "resend": {"transport": "resend", "key": "rk"},
                "ses": {"transport": "ses", "key": "k", "secret": "s"},
                "cloudflare": {
                    "transport": "cloudflare",
                    "api_token": "t",
                    "account_id": "acct",
                },
            },
        }
    )
    Mail.set_manager(manager)
    for name in ("mailgun", "postmark", "resend", "ses", "cloudflare"):
        Mail.mailer(name).to("a@b.c").send(Welcome())


@pytest.mark.asyncio
async def test_notification_facade_ondemand_mailmessage_locale_custom() -> None:
    _array_manager()
    CustomChannel.sent.clear()
    user = User()
    await notify_now(user, Paid())
    await NotificationFacade.route("mail", "x@y.z").notify(Paid())
    await notify_now(user, CustomNote())
    assert CustomChannel.sent
    assert user.preferred_locale() == "sw"


@pytest.mark.asyncio
async def test_vonage_and_slack_channels() -> None:
    from almasix.client.facade import set_factory
    from almasix.client.factory import Factory

    class Sms(Notification):
        def via(self, notifiable):
            return ["vonage"]

        def to_vonage(self, notifiable):
            return VonageMessage().content("hi")

    class Slack(Notification):
        def via(self, notifiable):
            return ["slack"]

        def to_slack(self, notifiable):
            return SlackMessage().content("hi").section_block("body")

    set_factory(Factory())
    Http.fake(lambda req: Http.response({"ok": True, "messages": [{"status": "0"}]}, 200))
    user = User()
    await notify_now(user, Sms())
    await notify_now(user, Slack())


def test_attachable_protocol() -> None:
    class Doc:
        def to_mail_attachment(self) -> Attachment:
            return Attachment.from_data(b"PDF", "doc.pdf", mime="application/pdf")

    class WithDoc(Mailable):
        def envelope(self) -> Envelope:
            return Envelope(subject="Doc")

        def content(self) -> Content:
            return Content(text="see attach")

        def attachments(self):
            return [Doc()]

    manager = _array_manager()
    Mail.to("a@b.c").send(WithDoc())
    msg = manager.array_transport().sent_messages[-1]
    assert msg.attachments[0].name == "doc.pdf"
