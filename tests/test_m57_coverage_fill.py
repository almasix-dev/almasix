"""M57 coverage fill — ESP edge paths, façade, MailMessage, sendmail, composites."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from almasix.client import Http
from almasix.client.facade import set_factory
from almasix.client.factory import Factory
from almasix.events import Event, listen
from almasix.mail import Content, Envelope, Mail, Mailable
from almasix.mail.helpers import default_mail_config, mail
from almasix.mail.mailable import Address, Attachment, EmbeddedImage
from almasix.mail.mailer import MailManager
from almasix.mail.message import SentMessage
from almasix.mail.transports.cloudflare import CloudflareTransport
from almasix.mail.transports.composite import FailoverTransport, RoundRobinTransport
from almasix.mail.transports.http_base import response_status
from almasix.mail.transports.mailgun import MailgunTransport
from almasix.mail.transports.postmark import PostmarkTransport
from almasix.mail.transports.resend import ResendTransport
from almasix.mail.transports.sendmail import SendmailTransport
from almasix.mail.transports.ses import SesTransport
from almasix.mail.transports.smtp import SmtpTransport
from almasix.notifications import (
    MailMessage,
    Notifiable,
    Notification,
    NotificationSending,
    ShouldQueue,
    notify,
)
from almasix.notifications.anonymous import AnonymousNotifiable
from almasix.notifications.channels import ArrayChannel, LogChannel, SlackChannel, VonageChannel
from almasix.notifications.facade import Notification as NotificationFacade
from almasix.notifications.helpers import (
    default_notifications_config,
    default_services_config,
    set_sender,
)
from almasix.notifications.messages_builders import SlackMessage, VonageMessage
from almasix.notifications.sender import NotificationSender


@pytest.fixture(autouse=True)
def _m57_isolation() -> None:
    set_factory(Factory())
    set_sender(None)
    Event.flush()
    ArrayChannel.clear()
    yield
    set_factory(Factory())
    set_sender(None)
    Event.flush()
    ArrayChannel.clear()


class Plain(Mailable):
    def envelope(self) -> Envelope:
        return Envelope(
            subject="S",
            from_address=Address("a@b.c", "A"),
            reply_to=[Address("r@b.c")],
            headers={"X-H": "1"},
        )

    def content(self) -> Content:
        return Content(html="<p>h</p>", text="t")

    def embeds(self) -> list[EmbeddedImage]:
        return [EmbeddedImage(content_id="x", data=b"img", mime="image/png", name="x.png")]

    def with_message(self, message) -> None:
        message.headers["X-Mut"] = "1"


def test_response_status_helper() -> None:
    class Prop:
        status = 418

    class Meth:
        def status(self) -> int:
            return 503

    assert response_status(Prop()) == 418
    assert response_status(Meth()) == 503
    assert response_status(object()) == "?"


def test_default_configs_and_mail_helper() -> None:
    assert "mailgun" in default_mail_config()["mailers"]
    assert "vonage" in default_services_config()
    assert "broadcast" in default_notifications_config()["channels"]
    manager = MailManager(config=default_mail_config())
    Mail.set_manager(manager)
    assert mail("log").name == "log"


def test_always_to_and_address_parse_and_smtp_build(tmp_path: Path) -> None:
    path = tmp_path / "a.pdf"
    path.write_bytes(b"%PDF")
    manager = MailManager(
        config={
            "default": "array",
            "from": {"address": "from@t"},
            "to": {"address": "catch@t", "name": "Catch"},
            "mailers": {"array": {"transport": "array"}},
        }
    )
    Mail.set_manager(manager)

    class WithAttach(Mailable):
        def envelope(self) -> Envelope:
            return Envelope(subject="A")

        def content(self) -> Content:
            return Content(text="hi")

        def attachments(self):
            return [
                Attachment.from_path(str(path)),
                Attachment.from_attachable(
                    type(
                        "O",
                        (),
                        {"to_mail_attachment": lambda self: Attachment.from_data(b"x", "x.bin")},
                    )()
                ),
            ]

    Mail.to("ignored@t").cc("c@t").send(WithAttach())
    msg = manager.array_transport().sent_messages[-1]
    assert msg.to[0].address == "catch@t"
    assert not msg.cc
    assert Address.parse(None) is None
    assert Address.parse("Name <n@e.com>").name == "Name"
    assert Address.parse_many(["a@b.c", ("c@d.e", "C")])

    built = SmtpTransport._build_email(
        SentMessage(
            mailable=None,
            to=[Address("t@e.com")],
            cc=[Address("c@e.com")],
            subject="S",
            html="<p>h</p>",
            text="t",
            from_address=Address("f@e.com", "F"),
            reply_to=[Address("r@e.com")],
            headers={"X-H": "1"},
            embeds=[EmbeddedImage(content_id="logo", data=b"PNG", mime="image/png")],
            attachments=[],
        )
    )
    assert built["Subject"] == "S"


def test_mailable_queue_locale_mailer_hooks() -> None:
    m = Plain().set_locale("sw").on_queue("emails").on_connection("redis").mailer("array")
    assert m.locale == "sw"
    assert m.queue == "emails"
    assert m.connection == "redis"
    assert m.mailer_name == "array"
    assert m.render()


def test_failover_and_roundrobin_failures() -> None:
    class Boom:
        def send(self, message):
            raise RuntimeError("nope")

    class Ok:
        def send(self, message):
            self.sent = True

    ok = Ok()
    transports = {"a": Boom(), "b": ok}

    def resolve(name):
        return transports[name]

    FailoverTransport(resolve, ["a", "b"], retry_after=1).send(MagicMock())
    assert ok.sent
    with pytest.raises(RuntimeError):
        FailoverTransport(resolve, ["a"], retry_after=0).send(MagicMock())
    with pytest.raises(RuntimeError):
        RoundRobinTransport(resolve, []).send(MagicMock())
    with pytest.raises(RuntimeError):
        RoundRobinTransport(resolve, ["a"]).send(MagicMock())


def test_sendmail_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    msg = SentMessage(mailable=None, to=[Address("t@e.com")], subject="S", text="hi")
    transport = SendmailTransport(path="/no/such/sendmail -bs")
    with pytest.raises(RuntimeError, match="not found"):
        transport.send(msg)

    class Proc:
        returncode = 1
        stderr = b"fail"

    monkeypatch.setattr("almasix.mail.transports.sendmail.subprocess.run", lambda *a, **k: Proc())
    with pytest.raises(RuntimeError, match="Sendmail failed"):
        SendmailTransport(path="/usr/sbin/sendmail -bs").send(msg)

    class Good:
        returncode = 0
        stderr = b""

    monkeypatch.setattr("almasix.mail.transports.sendmail.subprocess.run", lambda *a, **k: Good())
    SendmailTransport(path="/usr/sbin/sendmail -t").send(msg)
    SendmailTransport(path="/usr/sbin/sendmail").send(msg)

    def missing(*a, **k):
        raise FileNotFoundError("gone")

    monkeypatch.setattr("almasix.mail.transports.sendmail.subprocess.run", missing)
    with pytest.raises(RuntimeError, match="not found"):
        SendmailTransport(path="/usr/sbin/sendmail -t").send(msg)


def test_esp_from_config_and_failures() -> None:
    services = {
        "mailgun": {"domain": "d", "secret": "s"},
        "postmark": {"token": "t"},
        "resend": {"key": "k"},
        "ses": {"key": "k", "secret": "s", "region": "eu-west-1"},
        "cloudflare": {"api_token": "t", "account_id": "a"},
    }
    assert MailgunTransport.from_config({}, services).domain == "d"
    assert PostmarkTransport.from_config({}, services).token == "t"
    assert ResendTransport.from_config({}, services).key == "k"
    assert SesTransport.from_config({}, services).region == "eu-west-1"
    assert CloudflareTransport.from_config({}, services).account_id == "a"

    set_factory(Factory())
    Http.fake(lambda req: Http.response("nope", 500))
    msg = SentMessage(
        mailable=None,
        to=[Address("t@e.com")],
        cc=[Address("c@e.com")],
        bcc=[Address("b@e.com")],
        subject="S",
        html="<p>h</p>",
        text="t",
        from_address=Address("f@e.com", "F"),
        tags=["tag"],
        metadata={"m": "1"},
    )
    with pytest.raises(RuntimeError):
        MailgunTransport(domain="d", secret="s").send(msg)
    with pytest.raises(RuntimeError):
        PostmarkTransport(token="t").send(msg)
    with pytest.raises(RuntimeError):
        ResendTransport(key="k").send(msg)
    with pytest.raises(RuntimeError):
        SesTransport(key="k", secret="s").send(msg)
    with pytest.raises(RuntimeError):
        CloudflareTransport(api_token="t", account_id="a").send(msg)

    set_factory(Factory())
    Http.fake(lambda req: Http.response({"ok": True}, 200))
    MailgunTransport(domain="d", secret="s").send(msg)
    PostmarkTransport(token="t").send(msg)
    ResendTransport(key="k").send(msg)
    SesTransport(key="k", secret="s").send(msg)
    CloudflareTransport(api_token="t", account_id="a").send(
        SentMessage(mailable=None, to=[Address("t@e.com")], subject="S", text="t")
    )

    # Cloudflare treats 404 as a soft miss (record metadata anyway).
    set_factory(Factory())
    Http.fake(lambda req: Http.response("gone", 404))
    CloudflareTransport(api_token="t", account_id="a").send(
        SentMessage(mailable=None, to=[Address("t@e.com")], subject="S", text="t")
    )


def test_mail_message_fluent_surface() -> None:
    built = (
        MailMessage()
        .subject("Sub")
        .greeting("Hi")
        .lines(["a", "b"])
        .action("Go", "https://x.test")
        .line("outro")
        .success()
        .error()
        .from_("f@e.com", "F")
        .reply_to("r@e.com")
        .mailer("array")
        .attach("/tmp/x.pdf")
        .attach_data(b"x", "x.bin")
        .tag("t")
        .metadata("k", "v")
        .to_mailable()
    )
    assert built.envelope().subject == "Sub"
    assert built.mailer_name == "array"
    assert built.content().html
    assert built.attachments()


@pytest.mark.asyncio
async def test_notification_facade_send_locale_fake_and_events() -> None:
    Mail.set_manager(
        MailManager(
            config={
                "default": "array",
                "from": {"address": "f@t"},
                "mailers": {"array": {"transport": "array"}},
            }
        )
    )

    class User(Notifiable):
        email = "u@t"
        id = 1

        def get_key(self):
            return self.id

    class Note(Notification):
        def via(self, notifiable):
            return ["array"]

        def to_array(self, notifiable):
            return {"ok": True}

    class Queued(ShouldQueue, Note):
        delay = 1
        queue = "slow"

    aborted: list[str] = []

    def abort(e: NotificationSending):
        if e.channel == "array":
            aborted.append(e.channel)
            return False
        return None

    listen(NotificationSending, abort)
    await NotificationSender().send_now(User(), Note())
    assert aborted
    Event.flush()

    fake = NotificationFacade.fake()
    NotificationFacade.locale("sw").send([User()], Note())
    NotificationFacade.send_now(User(), Note())
    fake.assert_sent_times(Note, 2)
    assert isinstance(NotificationFacade.route("mail", "x@y.z"), AnonymousNotifiable)
    set_sender(None)

    await AnonymousNotifiable().route("array", "x").notify_now(Note())

    class NoRoute(Notifiable):
        pass

    with pytest.raises(ValueError):
        await VonageChannel().send(
            NoRoute(), type("N", (Notification,), {"to_vonage": lambda s, n: "hi"})()
        )

    set_factory(Factory())
    Http.fake(lambda req: Http.response("bad", 500))

    class Sms(Notification):
        def via(self, n):
            return ["vonage"]

        def to_vonage(self, n):
            return VonageMessage().content("c").from_("Acme").unicode_().client_reference_("1")

    class U(Notifiable):
        def route_notification_for_vonage(self):
            return "+1"

        def route_notification_for_slack(self):
            return "https://hooks.slack.com/services/x"

    with pytest.raises(RuntimeError):
        await VonageChannel().send(U(), Sms())
    with pytest.raises(RuntimeError):
        await SlackChannel().send(
            U(),
            type(
                "S",
                (Notification,),
                {"to_slack": lambda s, n: SlackMessage().content("c").header_block("h").to("#x")},
            )(),
        )

    set_factory(Factory())
    Http.fake(lambda req: Http.response({"ok": True}, 200))
    await SlackChannel().send(
        U(),
        type("S", (Notification,), {"to_slack": lambda s, n: {"text": "hi"}})(),
    )
    await LogChannel().send(User(), Note())
    await notify(User(), Note())

    with patch.object(NotificationSender, "_try_queue", return_value=False):
        results = await NotificationSender().send(User(), Queued())
        assert results


def test_later_delay_helpers() -> None:
    from almasix.mail.mailer import _delay_seconds

    assert _delay_seconds(5) == 5
    assert _delay_seconds(timedelta(seconds=3)) == 3
    assert _delay_seconds(datetime.now() + timedelta(seconds=10)) >= 0


def test_unsupported_transport() -> None:
    manager = MailManager(config={"default": "x", "mailers": {"x": {"transport": "nope"}}})
    with pytest.raises(ValueError):
        manager.mailer("x")
    with pytest.raises(KeyError):
        manager.mailer("missing")
