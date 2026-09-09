"""M12 unit tests — Mailable, Mailer, transports, assertions."""

from __future__ import annotations

import logging
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from almasix.filesystem.manager import Storage, StorageManager
from almasix.framework import Application
from almasix.mail import (
    Address,
    Attachment,
    Content,
    Envelope,
    Mail,
    Mailable,
    MailAssertions,
    ShouldQueue,
)
from almasix.mail.helpers import default_mail_config, mail
from almasix.mail.mailer import MailManager
from almasix.mail.markdown import render_content
from almasix.mail.provider import MailServiceProvider
from almasix.mail.transports.log import LogTransport
from almasix.mail.transports.smtp import SmtpTransport
from almasix.prism.engine import Engine
from almasix.prism.helpers import set_engine


@pytest.fixture
def mail_app(tmp_path: Path) -> Application:
    app = Application(base_path=tmp_path)
    app.config.set(
        "mail",
        {
            **default_mail_config(),
            "default": "array",
        },
    )
    MailServiceProvider(app).register()
    MailServiceProvider(app).boot()
    return app


class WelcomeMail(Mailable):
    def envelope(self) -> Envelope:
        return Envelope(subject="Welcome aboard")

    def content(self) -> Content:
        return Content(
            html="<p>Hello</p>",
            text="Hello",
        )


class InvoiceMail(Mailable):
    def __init__(self, invoice_id: str) -> None:
        self.invoice_id = invoice_id

    def envelope(self) -> Envelope:
        return Envelope(
            subject=f"Invoice {self.invoice_id}",
            from_address=Address("billing@example.com", "Billing"),
            reply_to=[Address("support@example.com")],
            tags=["invoice"],
            metadata={"invoice_id": self.invoice_id},
        )

    def content(self) -> Content:
        return Content(text=f"Invoice body {self.invoice_id}")

    def attachments(self) -> list[Attachment]:
        return [Attachment.from_data(b"pdf-bytes", "invoice.pdf", mime="application/pdf")]


class QueuedMail(Mailable, ShouldQueue):
    def envelope(self) -> Envelope:
        return Envelope(subject="Queued")

    def content(self) -> Content:
        return Content(text="Later")


def test_address_parse() -> None:
    assert Address.parse("user@example.com") == Address("user@example.com")
    assert Address.parse("Name <user@example.com>") == Address("user@example.com", "Name")
    assert Address.parse(("user@example.com", "Name")) == Address("user@example.com", "Name")


def test_array_transport_send_and_assertions(mail_app: Application) -> None:
    assertions = MailAssertions("array")
    assertions.flush()

    Mail.to("user@example.com").send(WelcomeMail())

    def _check(message: Any) -> None:
        assert message.subject == "Welcome aboard"

    assertions.assert_sent(WelcomeMail, _check)
    assertions.assert_not_sent(InvoiceMail)
    assertions.assert_nothing_queued()


def test_pending_mail_recipients_and_envelope(mail_app: Application) -> None:
    assertions = MailAssertions("array")
    assertions.flush()

    message = (
        Mail.to("one@example.com", ("two@example.com", "Two"))
        .cc("cc@example.com")
        .bcc("bcc@example.com")
        .send(InvoiceMail("42"))
    )
    assert message is not None
    assert message.to[0].address == "one@example.com"
    assert message.to[1] == Address("two@example.com", "Two")
    assert message.cc[0].address == "cc@example.com"
    assert message.bcc[0].address == "bcc@example.com"
    assert message.from_address == Address("billing@example.com", "Billing")
    assert message.reply_to[0].address == "support@example.com"
    assert message.attachments[0].name == "invoice.pdf"
    assertions.assert_sent(InvoiceMail)


def test_path_and_storage_attachments(mail_app: Application, tmp_path: Path) -> None:
    attachment_path = tmp_path / "note.txt"
    attachment_path.write_text("hello attachment", encoding="utf-8")

    fs_config = {
        "default": "memory",
        "disks": {"memory": {"driver": "memory"}},
    }
    manager = StorageManager(mail_app, fs_config)
    Storage.set_manager(manager)
    manager.disk("memory").put("docs/readme.txt", b"storage attachment")

    class FileMail(Mailable):
        def envelope(self) -> Envelope:
            return Envelope(subject="Files")

        def content(self) -> Content:
            return Content(text="files")

        def attachments(self) -> list[Attachment]:
            return [
                Attachment.from_path(str(attachment_path)),
                Attachment.from_storage("docs/readme.txt", disk="memory", name="readme.txt"),
            ]

    assertions = MailAssertions("array")
    assertions.flush()
    Mail.to("user@example.com").send(FileMail())
    sent = assertions.assert_sent(FileMail)
    assert len(sent.attachments) == 2
    assert sent.attachments[0].data == b"hello attachment"
    assert sent.attachments[1].data == b"storage attachment"


def test_log_transport_writes_logger() -> None:
    from almasix.log.manager import get_logger
    from almasix.mail.message import SentMessage

    records: list[str] = []
    logger = get_logger()
    handler = logging.Handler()
    handler.emit = lambda record: records.append(record.getMessage())  # type: ignore[method-assign]
    logger.addHandler(handler)

    transport = LogTransport()
    message = SentMessage(
        mailable=WelcomeMail(),
        to=[Address("user@example.com")],
        subject="Welcome aboard",
        text="Hello",
    )
    transport.send(message)
    assert any("Mail sent:" in record for record in records)


def test_markdown_render_with_prism(tmp_path: Path) -> None:
    views = tmp_path / "resources" / "views"
    mail_views = views / "mail"
    mail_views.mkdir(parents=True)
    (mail_views / "welcome.prism.html").write_text("<p>Hello {{ name }}</p>", encoding="utf-8")
    (mail_views / "welcome.text.prism.html").write_text("Hello {{ name }}", encoding="utf-8")

    engine = Engine(paths=[views], cache_enabled=False)
    set_engine(engine)

    html_body, text_body = render_content(
        Content(markdown="mail.welcome", with_data={"name": "Almasix"})
    )
    assert html_body is not None
    assert "Hello Almasix" in html_body
    assert "almasix-dump" not in html_body
    assert text_body == "Hello Almasix"


def test_markdown_html_fallback_without_text_view() -> None:
    html_body, text_body = render_content(Content(html="<p>Hi <strong>there</strong></p>"))
    assert html_body == "<p>Hi <strong>there</strong></p>"
    assert text_body == "Hi there"


def test_smtp_transport_builds_email(mail_app: Application) -> None:
    client = MagicMock()
    transport = SmtpTransport(client=client)
    message = Mail.to("user@example.com").send(WelcomeMail())
    assert message is not None
    transport.send(message)
    client.send_message.assert_called_once()
    email = client.send_message.call_args.args[0]
    assert isinstance(email, EmailMessage)
    assert email["Subject"] == "Welcome aboard"


def test_queue_records_on_array_transport(mail_app: Application) -> None:
    assertions = MailAssertions("array")
    assertions.flush()
    Mail.to("user@example.com").queue(QueuedMail())
    assertions.assert_queued(QueuedMail)
    assertions.assert_nothing_sent()


def test_should_queue_mailable_send_queues(mail_app: Application) -> None:
    assertions = MailAssertions("array")
    assertions.flush()
    Mail.to("user@example.com").send(QueuedMail())
    assertions.assert_queued(QueuedMail)
    assertions.assert_nothing_sent()


def test_mail_helper_resolves_mailer(mail_app: Application) -> None:
    assert mail("array").name == "array"


def test_default_mail_config_shape() -> None:
    config = default_mail_config()
    assert config["default"] == "log"
    assert "smtp" in config["mailers"]
    assert config["mailers"]["log"]["transport"] == "log"
    assert config["mailers"]["array"]["transport"] == "array"


def test_provider_uses_default_config(tmp_path: Path) -> None:
    app = Application(base_path=tmp_path)
    MailServiceProvider(app).register()
    MailServiceProvider(app).boot()
    manager = app.make(MailManager)
    assert manager.get_default_mailer() == "log"
    assert manager.default_from() == Address("hello@example.com", "Example")
