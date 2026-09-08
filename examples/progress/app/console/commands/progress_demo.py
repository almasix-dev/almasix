"""Progress living demos — queues, mail, notifications (M11–M13)."""

from __future__ import annotations

from almasix.console import Command
from almasix.mail import Attachment, Content, Envelope, Mail, Mailable, ShouldQueue
from almasix.notifications import MustVerifyEmail, Notifiable, ResetPasswordNotification
from almasix.queue import Job, ShouldQueue as QueueShouldQueue, dispatch


class ProgressDigestJob(QueueShouldQueue, Job):
    """Demo job processed by ``python smith queue:work`` (database) or sync."""

    tries = 2

    def __init__(self, message: str = "digest") -> None:
        self.message = message

    def handle(self) -> None:
        from pathlib import Path

        stamp = Path("storage/framework/progress-job.txt")
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(f"ran:{self.message}\n", encoding="utf-8")


class WelcomeMail(ShouldQueue, Mailable):
    def __init__(self, name: str = "Artisan") -> None:
        self.name = name

    def envelope(self) -> Envelope:
        return Envelope(subject="Welcome to Progress")

    def content(self) -> Content:
        return Content(
            markdown="mail.welcome",
            with_data={
                "name": self.name,
                "app_name": "Progress",
                "board_url": "/progress",
                "subject": "Welcome to Progress",
            },
        )


class ProgressDemoCommand(Command):
    signature = "progress:demo {which=all}"
    description = "Run M11–M13 living demos (queue, mail, notifications)"

    def handle(self) -> int:
        which = str(self.argument("which") or "all")
        if which in {"all", "queue", "job"}:
            self._demo_queue()
        if which in {"all", "mail"}:
            self._demo_mail()
        if which in {"all", "notify", "notifications"}:
            self._demo_notify()
        return 0

    def _demo_queue(self) -> None:
        import asyncio

        asyncio.run(dispatch(ProgressDigestJob("progress:demo")))
        self.info("Dispatched ProgressDigestJob (sync connection runs immediately).")
        self.comment("With QUEUE_CONNECTION=database: python smith queue:work --once")

    def _demo_mail(self) -> None:
        Mail.to("demo@progress.test").send(WelcomeMail("Progress"))
        self.info("Sent WelcomeMail (log/array per MAIL_MAILER).")

    def _demo_notify(self) -> None:
        import asyncio

        class Guest(Notifiable, MustVerifyEmail):
            email = "demo@progress.test"
            id = 0
            email_verified_at = None

            def get_key(self) -> int:
                return 0

        guest = Guest()
        asyncio.run(guest.notify(ResetPasswordNotification("demo-token")))
        asyncio.run(guest.send_email_verification_notification())
        self.info("Sent ResetPasswordNotification + VerifyEmailNotification.")
