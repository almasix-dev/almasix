"""M12 coverage fill — edge cases and assertion branches."""

from __future__ import annotations

import smtplib
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from almasix.prism.engine import Engine
from almasix.prism.helpers import set_engine
from almasix.framework import Application
from almasix.mail import Address, Attachment, Content, Envelope, Mail, MailAssertions, Mailable
from almasix.mail.helpers import default_mail_config
from almasix.mail.mailer import MailManager, PendingMail, _read_storage, _resolve_attachments
from almasix.mail.message import ResolvedAttachment, SentMessage
from almasix.mail.provider import MailServiceProvider
from almasix.mail.testing import MailAssertions as Assertions
from almasix.mail.transports.smtp import SmtpTransport


class PlainMail(Mailable):
    def envelope(self) -> Envelope:
        return Envelope(subject="Plain")

    def content(self) -> Content:
        return Content(view="pages.plain", with_data={"title": "Plain"})


def _array_app(tmp_path: Path) -> Application:
    app = Application(base_path=tmp_path)
    app.config.set("mail", {**default_mail_config(), "default": "array"})
    MailServiceProvider(app).register()
    MailServiceProvider(app).boot()
    return app


def test_mail_manager_errors() -> None:
    manager = MailManager(config={"default": "log", "mailers": {}})
    with pytest.raises(KeyError, match="Mailer \\[missing\\]"):
        manager.mailer("missing")
    with pytest.raises(ValueError, match="Unsupported mail transport"):
        manager.set_config(
            {
                "default": "bad",
                "mailers": {"bad": {"transport": "carrier-pigeon"}},
            }
        )
        manager.mailer("bad")


def test_mail_static_facade_methods(tmp_path: Path) -> None:
    _array_app(tmp_path)
    Mail.send(PlainMail())
    Mail.queue(PlainMail())
    assert Mail.manager().get_default_mailer() == "array"


def test_attachment_validation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires path, storage_path, or data"):
        _resolve_attachments([Attachment()], tmp_path)
    with pytest.raises(ValueError, match="requires a file name"):
        _resolve_attachments([Attachment.from_data(b"x", "")], tmp_path)


def test_storage_attachment_failure() -> None:
    with pytest.raises(RuntimeError, match="Unable to read attachment"):
        _read_storage("missing", "file.txt")


def test_sent_message_has_recipient() -> None:
    message = SentMessage(
        mailable=PlainMail(),
        to=[Address("a@example.com")],
        cc=[Address("b@example.com")],
        bcc=[Address("c@example.com")],
    )
    assert message.has_recipient("b@example.com")
    assert not message.has_recipient("z@example.com")


def test_address_parse_edges() -> None:
    assert Address.parse(None) is None
    assert Address.parse("") is None
    assert Address.parse(Address("x@example.com")) == Address("x@example.com")
    assert Address.parse_many(["a@example.com", ("b@example.com", "B")])[1].name == "B"


def test_assertion_helpers_failures(tmp_path: Path) -> None:
    _array_app(tmp_path)
    assertions = Assertions("array")
    assertions.flush()

    with pytest.raises(AssertionError, match="No mailable"):
        assertions.assert_sent(PlainMail)
    with pytest.raises(AssertionError, match="Expected no mail"):
        Mail.to("x@example.com").send(PlainMail())
        assertions.assert_nothing_sent()
    with pytest.raises(AssertionError, match="was sent unexpectedly"):
        assertions.assert_not_sent(PlainMail)
    with pytest.raises(AssertionError, match="No mailable"):
        assertions.assert_queued(PlainMail)
    with pytest.raises(AssertionError, match="Expected no mail to be queued"):
        Mail.to("x@example.com").queue(PlainMail())
        assertions.assert_nothing_queued()
    with pytest.raises(AssertionError, match="was queued unexpectedly"):
        assertions.assert_not_queued(PlainMail)


def test_assertions_require_array_transport(tmp_path: Path) -> None:
    app = Application(base_path=tmp_path)
    app.config.set("mail", {**default_mail_config(), "default": "log"})
    MailServiceProvider(app).register()
    MailServiceProvider(app).boot()
    with pytest.raises(RuntimeError, match="array transport"):
        Assertions("log").transport


def test_smtp_transport_connect_and_variants() -> None:
    message = SentMessage(
        mailable=PlainMail(),
        to=[Address("to@example.com")],
        cc=[Address("cc@example.com")],
        bcc=[Address("bcc@example.com")],
        subject="Subject",
        html="<b>Hi</b>",
        text="Hi",
        from_address=Address("from@example.com", "From"),
        reply_to=[Address("reply@example.com")],
    )

    ssl_client = MagicMock()
    with patch("almasix.mail.transports.smtp.smtplib.SMTP_SSL", return_value=ssl_client):
        SmtpTransport(encryption="ssl").send(message)
    ssl_client.send_message.assert_called_once()
    ssl_client.quit.assert_called_once()

    tls_client = MagicMock()
    with patch("almasix.mail.transports.smtp.smtplib.SMTP", return_value=tls_client):
        SmtpTransport(encryption="tls", username="user", password="secret").send(message)
    tls_client.starttls.assert_called_once()
    tls_client.login.assert_called_once_with("user", "secret")

    html_only = SentMessage(
        mailable=PlainMail(),
        to=[Address("to@example.com")],
        subject="HTML",
        html="<p>Only HTML</p>",
    )
    text_only = SentMessage(
        mailable=PlainMail(),
        to=[Address("to@example.com")],
        subject="Text",
        text="Only text",
    )
    empty = SentMessage(mailable=PlainMail(), to=[Address("to@example.com")], subject="Empty")
    SmtpTransport(client=MagicMock()).send(html_only)
    SmtpTransport(client=MagicMock()).send(text_only)
    SmtpTransport(client=MagicMock()).send(empty)


def test_markdown_view_branch(tmp_path: Path) -> None:
    views = tmp_path / "views"
    views.mkdir()
    (views / "pages.prism.html").write_text("<div>{{ title }}</div>", encoding="utf-8")
    set_engine(Engine(paths=[views], cache_enabled=False))
    from almasix.mail.markdown import render_content

    html_body, text_body = render_content(Content(view="pages", with_data={"title": "View"}))
    assert html_body == "<div>View</div>"
    assert text_body == "View"


def test_dispatch_to_queue_with_queue_provider(tmp_path: Path) -> None:
    app = Application(base_path=tmp_path)
    app.config.set("mail", {**default_mail_config(), "default": "array"})
    app.config.set(
        "queue",
        {
            "default": "sync",
            "connections": {"sync": {"driver": "sync"}},
        },
    )
    from almasix.queue.provider import QueueServiceProvider

    MailServiceProvider(app).register()
    QueueServiceProvider(app).register()
    MailServiceProvider(app).boot()
    QueueServiceProvider(app).boot()

    assertions = Assertions("array")
    assertions.flush()
    Mail.to("user@example.com").queue(PlainMail())
    assertions.assert_queued(PlainMail)


def test_pending_mail_direct_mailer_send(tmp_path: Path) -> None:
    _array_app(tmp_path)
    mailer = Mail.mailer("array")
    sent = mailer.send(PlainMail(), to=[Address("direct@example.com")])
    assert sent is not None
    assert sent.to[0].address == "direct@example.com"
    queued = mailer.queue(PlainMail(), to=[Address("queued@example.com")])
    assert queued is not None
    assert queued.to[0].address == "queued@example.com"


def test_mailable_defaults() -> None:
    base = Mailable()
    assert base.envelope().subject == ""
    assert base.content().html is None
    assert base.attachments() == []


def test_smtp_mailer_resolution_and_default_from() -> None:
    manager = MailManager(
        config={
            "default": "smtp",
            "from": {},
            "mailers": {
                "smtp": {
                    "transport": "smtp",
                    "host": "smtp.test",
                    "port": 587,
                }
            },
        }
    )
    assert manager.default_from() is None
    mailer = manager.mailer("smtp")
    assert isinstance(mailer.transport, SmtpTransport)


def test_queue_sync_fallback_on_log_transport(tmp_path: Path) -> None:
    app = Application(base_path=tmp_path)
    app.config.set("mail", {**default_mail_config(), "default": "log"})
    MailServiceProvider(app).register()
    MailServiceProvider(app).boot()
    Mail.to("user@example.com").queue(PlainMail())


def test_mail_manager_without_bootstrapped_manager() -> None:
    Mail.set_manager(None)
    assert Mail.manager().get_default_mailer() == "log"


def test_absolute_path_attachment_without_app(tmp_path: Path) -> None:
    path = tmp_path / "file.bin"
    path.write_bytes(b"bin")
    resolved = _resolve_attachments([Attachment.from_path(str(path))], None)
    assert resolved[0].data == b"bin"


def test_assert_queued_callback_and_string_filter(tmp_path: Path) -> None:
    _array_app(tmp_path)
    assertions = Assertions("array")
    assertions.flush()
    Mail.to("user@example.com").queue(PlainMail())
    seen: list[str] = []

    def _check(message: SentMessage) -> None:
        seen.append(message.subject)

    assertions.assert_queued("PlainMail", _check)
    assert seen == ["Plain"]


def test_smtp_from_without_name_and_attachment_mime() -> None:
    message = SentMessage(
        mailable=PlainMail(),
        to=[Address("to@example.com")],
        subject="Attach",
        text="Body",
        from_address=Address("from@example.com"),
        attachments=[
            ResolvedAttachment(
                name="file.bin",
                data=b"123",
                mime="octet-stream",
            )
        ],
    )
    SmtpTransport(client=MagicMock()).send(message)


@pytest.mark.asyncio
async def test_dispatch_to_queue_in_running_loop(tmp_path: Path) -> None:
    app = Application(base_path=tmp_path)
    app.config.set("mail", {**default_mail_config(), "default": "array"})
    app.config.set(
        "queue",
        {
            "default": "sync",
            "connections": {"sync": {"driver": "sync"}},
        },
    )
    from almasix.queue.provider import QueueServiceProvider

    MailServiceProvider(app).register()
    QueueServiceProvider(app).register()
    MailServiceProvider(app).boot()
    QueueServiceProvider(app).boot()
    Mail.to("user@example.com").queue(PlainMail())


def test_mail_to_static_method(tmp_path: Path) -> None:
    _array_app(tmp_path)
    message = Mail.to("static@example.com").send(PlainMail())
    assert message is not None
    assert message.to[0].address == "static@example.com"


def test_relative_path_attachment_with_app(tmp_path: Path) -> None:
    app = Application(base_path=tmp_path)
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    (storage_dir / "doc.txt").write_text("relative", encoding="utf-8")
    resolved = _resolve_attachments([Attachment.from_path("storage/doc.txt")], app)
    assert resolved[0].data == b"relative"


def test_queue_sync_fallback_when_dispatch_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = Application(base_path=tmp_path)
    app.config.set("mail", {**default_mail_config(), "default": "log"})
    MailServiceProvider(app).register()
    MailServiceProvider(app).boot()
    monkeypatch.setattr("almasix.mail.mailer._dispatch_to_queue", lambda *_args: False)
    Mail.to("user@example.com").queue(PlainMail())


def test_dispatch_to_queue_import_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    real_import = builtins.__import__

    def blocked_import(
        name: str,
        globals: dict[str, Any] | None = None,
        locals: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "almasix.queue.helpers":
            raise ImportError("queue unavailable")
        return real_import(name, globals, locals, fromlist, level)

    _array_app(tmp_path)
    monkeypatch.setattr(builtins, "__import__", blocked_import)
    Mail.to("user@example.com").queue(PlainMail())
