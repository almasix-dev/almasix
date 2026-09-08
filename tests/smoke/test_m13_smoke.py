"""M13 smoke — Notifiable User + reset notification path."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from almasix.console.kernel import ConsoleKernel
from almasix.mail import Mail
from almasix.notifications import ResetPasswordNotification
from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke, pytest.mark.regression]

PROGRESS = Path(__file__).resolve().parents[2] / "examples" / "progress"


@pytest.fixture()
def progress_cwd(monkeypatch: pytest.MonkeyPatch) -> Path:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    monkeypatch.setenv("MAIL_MAILER", "array")
    yield PROGRESS
    purge_generated_app_modules()
    while str(PROGRESS) in sys.path:
        sys.path.remove(str(PROGRESS))


@pytest.mark.asyncio
async def test_m13_user_notifiable(progress_cwd: Path) -> None:
    kernel = ConsoleKernel.from_cwd(progress_cwd)
    kernel.app.config.set("mail.default", "array")
    from almasix.mail.provider import MailServiceProvider
    from almasix.notifications.provider import NotificationServiceProvider

    MailServiceProvider(kernel.app).register()
    MailServiceProvider(kernel.app).boot()
    NotificationServiceProvider(kernel.app).register()
    NotificationServiceProvider(kernel.app).boot()

    from app.models.user import User

    assert issubclass(User, __import__("almasix.notifications", fromlist=["Notifiable"]).Notifiable)
    user = User(attributes={"email": "smoke@progress.test", "name": "Smoke"})
    await user.notify(ResetPasswordNotification("smoke-token"))
    transport = Mail.manager().array_transport()
    assert transport is not None
    assert transport.sent_messages
