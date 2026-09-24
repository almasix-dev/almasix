"""M13 notifications tests — Notifiable, channels, verification, reset mail."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from almasix.framework import Application
from almasix.mail import Mail
from almasix.mail.helpers import default_mail_config
from almasix.mail.provider import MailServiceProvider
from almasix.notifications import (
    ArrayChannel,
    MustVerifyEmail,
    Notifiable,
    Notification,
    ResetPasswordNotification,
    VerifyEmailNotification,
    ensure_tables,
    notify,
    notify_now,
)
from almasix.notifications.channels import DatabaseChannel
from almasix.notifications.provider import NotificationServiceProvider
from almasix.notifications.sender import NotificationSender
from almasix.orm import DatabaseManager
from tests.orm_support import memory_db  # noqa: F401


class FakeUser(Notifiable, MustVerifyEmail):
    def __init__(self, email: str = "ada@example.com", user_id: int = 1) -> None:
        self.email = email
        self.id = user_id
        self.email_verified_at = None
        self._attrs: dict[str, Any] = {"email": email, "email_verified_at": None}

    def get_key(self) -> int:
        return self.id

    def get_attribute(self, key: str) -> Any:
        return self._attrs.get(key)

    def set_attribute(self, key: str, value: Any) -> None:
        self._attrs[key] = value
        setattr(self, key, value)

    async def save(self) -> bool:
        return True


class WelcomeNotification(Notification):
    def via(self, notifiable: Any) -> list[str]:
        del notifiable
        return ["array", "log"]

    def to_array(self, notifiable: Any) -> dict[str, Any]:
        return {"hello": getattr(notifiable, "email", None)}

    def to_database(self, notifiable: Any) -> dict[str, Any]:
        return self.to_array(notifiable)


class MailNote(Notification):
    def via(self, notifiable: Any) -> list[str]:
        del notifiable
        return ["mail"]

    def to_mail(self, notifiable: Any) -> dict[str, Any]:
        return {
            "subject": "Hi",
            "text": f"Hello {getattr(notifiable, 'email', '')}",
            "html": "<p>Hello</p>",
        }


@pytest.fixture
def mail_ready(tmp_path: Path) -> Application:
    app = Application(base_path=tmp_path)
    app.config.set("mail", {**default_mail_config(), "default": "array"})
    MailServiceProvider(app).register()
    MailServiceProvider(app).boot()
    NotificationServiceProvider(app).register()
    NotificationServiceProvider(app).boot()
    return app


@pytest.mark.asyncio
async def test_array_and_log_channels(mail_ready: Application) -> None:
    del mail_ready
    ArrayChannel.clear()
    user = FakeUser()
    results = await notify_now(user, WelcomeNotification())
    assert len(results) == 2
    assert ArrayChannel.messages
    assert ArrayChannel.messages[-1]["payload"]["hello"] == "ada@example.com"


@pytest.mark.asyncio
async def test_mail_channel(mail_ready: Application) -> None:
    user = FakeUser()
    await notify_now(user, MailNote())
    transport = Mail.manager().array_transport()
    assert transport is not None
    assert transport.sent_messages
    assert transport.sent_messages[-1].subject == "Hi"


@pytest.mark.asyncio
async def test_database_channel(memory_db: DatabaseManager) -> None:
    del memory_db
    await ensure_tables()
    user = FakeUser()
    channel = DatabaseChannel()
    row = await channel.send(user, WelcomeNotification())
    assert row["id"]
    assert row["data"]["hello"] == "ada@example.com"
    unread = await user.unread_notifications()
    assert len(unread) == 1
    assert await user.mark_notification_as_read(unread[0]["id"])
    assert await user.unread_notifications() == []
    assert await user.mark_notification_as_unread(unread[0]["id"])
    assert len(await user.unread_notifications()) == 1
    await channel.send(user, WelcomeNotification())
    assert await user.mark_notifications_as_read() >= 1
    assert await user.unread_notifications() == []


@pytest.mark.asyncio
async def test_database_notification_model(memory_db: DatabaseManager) -> None:
    del memory_db
    from almasix.notifications import DatabaseNotification
    from almasix.notifications.database import DatabaseNotificationStore

    await ensure_tables()
    user = FakeUser()
    created = await DatabaseNotificationStore().create(
        user, WelcomeNotification(), {"hello": "world"}
    )
    row = await DatabaseNotification.find(created["id"])
    assert row is not None
    assert row.get_data()["hello"] == "world"
    assert row.is_unread()
    await row.mark_as_read()
    refreshed = await DatabaseNotification.find(created["id"])
    assert refreshed is not None
    assert refreshed.is_read()
    await refreshed.mark_as_unread()
    assert (await DatabaseNotification.find(created["id"])).is_unread()


def test_notifications_table_stub_columns() -> None:
    from pathlib import Path

    stub = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "almasix"
        / "console"
        / "stubs"
        / "migration.notifications.stub"
    )
    text = stub.read_text(encoding="utf-8")
    for needle in (
        'table.uuid("id").primary()',
        'table.string("type")',
        'table.string("notifiable_type")',
        'table.string("notifiable_id")',
        'table.text("data")',
        'table.timestamp("read_at").nullable()',
        "table.timestamps()",
    ):
        assert needle in text


def test_make_notifications_table_alias() -> None:
    from almasix.console.commands.tables import NotificationsTableCommand

    assert "make:notifications-table" in NotificationsTableCommand.aliases


@pytest.mark.asyncio
async def test_notifiable_notify_helper(mail_ready: Application) -> None:
    ArrayChannel.clear()
    user = FakeUser()
    await user.notify(WelcomeNotification())
    assert ArrayChannel.messages


@pytest.mark.asyncio
async def test_must_verify_email(mail_ready: Application) -> None:
    user = FakeUser()
    assert user.has_verified_email() is False
    await user.mark_email_as_verified()
    assert user.has_verified_email() is True
    url = user.verification_url(base_url="http://localhost")
    assert "email/verify" in url
    await user.send_email_verification_notification()
    transport = Mail.manager().array_transport()
    assert transport is not None
    assert any(m.subject == "Verify Email Address" for m in transport.sent_messages)


@pytest.mark.asyncio
async def test_reset_password_notification(mail_ready: Application) -> None:
    user = FakeUser()
    note = ResetPasswordNotification("token-123", reset_url="/reset?token=token-123")
    await notify(user, note)
    transport = Mail.manager().array_transport()
    assert transport is not None
    assert any("Reset Password" in (m.subject or "") for m in transport.sent_messages)


@pytest.mark.asyncio
async def test_password_broker_uses_notification(mail_ready: Application) -> None:
    from almasix.auth.passwords import PasswordBroker, get_password_manager

    class Provider:
        async def retrieve_by_credentials(self, credentials: dict[str, Any]) -> FakeUser | None:
            return FakeUser(email=str(credentials.get("email")))

    class Tokens:
        async def recently_created(self, email: str) -> bool:
            del email
            return False

        async def create(self, email: str) -> str:
            del email
            return "tok"

    # Provider boot already wired create_url_using — ensure callback fires.
    manager = get_password_manager()
    assert manager._send_callback is not None

    broker = PasswordBroker(Provider(), Tokens(), send_callback=manager._send_callback)
    status = await broker.send_reset_link({"email": "ada@example.com"})
    assert status == "passwords.sent" or "sent" in status
    transport = Mail.manager().array_transport()
    assert transport is not None
    assert transport.sent_messages


@pytest.mark.asyncio
async def test_sender_unknown_channel() -> None:
    with pytest.raises(KeyError):
        await NotificationSender().send_now(
            FakeUser(),
            SimpleNamespace(via=lambda n: ["nope"]),
        )


def test_verify_email_notification_builders() -> None:
    user = FakeUser()
    note = VerifyEmailNotification()
    assert note.via(user) == ["mail"]
    assert "verify-email" in note.to_database(user)["action"]
