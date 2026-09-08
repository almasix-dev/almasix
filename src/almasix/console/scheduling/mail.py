"""Emailing a task's output."""

from __future__ import annotations

from typing import TYPE_CHECKING

from almasix.mail.mailable import Content, Envelope, Mailable

if TYPE_CHECKING:
    from almasix.console.scheduling.event import Event


class ScheduledTaskOutput(Mailable):
    """The mail ``email_output_to`` sends: a subject, and the output as text."""

    def __init__(self, task: str, output: str, exit_code: int) -> None:
        self.task = task
        self.output = output
        self.exit_code = exit_code

    def envelope(self) -> Envelope:
        state = "output" if self.exit_code == 0 else f"failed with exit code {self.exit_code}"
        return Envelope(subject=f"Scheduled task {state}: {self.task}")

    def content(self) -> Content:
        return Content(text=self.output or "(no output)")


def mail_output(event: Event, output: str, exit_code: int) -> None:
    """Send one task's output to the addresses it named."""
    from almasix.mail.mailer import Mail

    Mail.to(*event.email_addresses).send(
        ScheduledTaskOutput(event.summary(), output, exit_code)
    )


__all__ = ["ScheduledTaskOutput", "mail_output"]
