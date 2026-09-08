"""M12 smoke — array mailer send in progress app."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from almasix.console.kernel import ConsoleKernel
from almasix.mail import Content, Envelope, Mail, Mailable
from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke, pytest.mark.regression]

PROGRESS = Path(__file__).resolve().parents[2] / "examples" / "progress"


class SmokeMail(Mailable):
    def envelope(self) -> Envelope:
        return Envelope(subject="Progress smoke")

    def content(self) -> Content:
        return Content(text="hello from M12")


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


def test_m12_mail_send_array(progress_cwd: Path) -> None:
    kernel = ConsoleKernel.from_cwd(progress_cwd)
    kernel.app.config.set("mail.default", "array")
    from almasix.mail.provider import MailServiceProvider

    MailServiceProvider(kernel.app).register()
    MailServiceProvider(kernel.app).boot()
    Mail.to("smoke@progress.test").send(SmokeMail())
    transport = Mail.manager().array_transport()
    assert transport is not None
    assert any(m.subject == "Progress smoke" for m in transport.sent_messages)
