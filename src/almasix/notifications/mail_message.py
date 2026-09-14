"""Fluent MailMessage builder for notification mail channel (Laravel MailMessage)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from almasix.mail.mailable import Attachment, Content, Envelope, Mailable


@dataclass
class MailMessage:
    """Laravel-shaped notification mail builder."""

    subject_line: str | None = None
    greeting_line: str | None = None
    intro_lines: list[str] = field(default_factory=list)
    outro_lines: list[str] = field(default_factory=list)
    action_text: str | None = None
    action_url: str | None = None
    level: str = "info"  # info | success | error
    from_address: str | None = None
    from_name: str | None = None
    reply_to_address: str | None = None
    mailer_name: str | None = None
    attachment_list: list[Attachment] = field(default_factory=list)
    tag_list: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def subject(self, subject: str) -> MailMessage:
        self.subject_line = subject
        return self

    def greeting(self, greeting: str) -> MailMessage:
        self.greeting_line = greeting
        return self

    def line(self, line: str) -> MailMessage:
        if self.action_text is None:
            self.intro_lines.append(line)
        else:
            self.outro_lines.append(line)
        return self

    def lines(self, lines: list[str]) -> MailMessage:
        for item in lines:
            self.line(item)
        return self

    def action(self, text: str, url: str) -> MailMessage:
        self.action_text = text
        self.action_url = url
        return self

    def success(self) -> MailMessage:
        self.level = "success"
        return self

    def error(self) -> MailMessage:
        self.level = "error"
        return self

    def from_(self, address: str, name: str | None = None) -> MailMessage:
        self.from_address = address
        self.from_name = name
        return self

    def reply_to(self, address: str) -> MailMessage:
        self.reply_to_address = address
        return self

    def mailer(self, name: str) -> MailMessage:
        self.mailer_name = name
        return self

    def attach(self, path: str, *, name: str | None = None, mime: str | None = None) -> MailMessage:
        self.attachment_list.append(Attachment.from_path(path, name=name, mime=mime))
        return self

    def attach_data(
        self,
        data: bytes,
        name: str,
        *,
        mime: str | None = None,
    ) -> MailMessage:
        self.attachment_list.append(Attachment.from_data(data, name, mime=mime))
        return self

    def tag(self, value: str) -> MailMessage:
        self.tag_list.append(value)
        return self

    def metadata(self, key: str, value: Any) -> MailMessage:
        self.meta[key] = value
        return self

    def to_mailable(self) -> Mailable:
        html_parts: list[str] = []
        text_parts: list[str] = []
        if self.greeting_line:
            html_parts.append(f"<p><strong>{_escape(self.greeting_line)}</strong></p>")
            text_parts.append(self.greeting_line)
        for line in self.intro_lines:
            html_parts.append(f"<p>{_escape(line)}</p>")
            text_parts.append(line)
        if self.action_text and self.action_url:
            html_parts.append(
                f'<p><a class="button" href="{_escape(self.action_url)}">'
                f"{_escape(self.action_text)}</a></p>"
            )
            text_parts.append(f"{self.action_text}: {self.action_url}")
        for line in self.outro_lines:
            html_parts.append(f"<p>{_escape(line)}</p>")
            text_parts.append(line)

        subject = self.subject_line or "Notification"
        from almasix.mail.mailable import Address

        envelope = Envelope(
            subject=subject,
            from_address=Address.parse(
                (self.from_address, self.from_name) if self.from_address else None
            ),
            reply_to=[Address.parse(self.reply_to_address)] if self.reply_to_address else [],
            tags=list(self.tag_list),
            metadata=dict(self.meta),
        )
        # Filter None reply_to
        envelope.reply_to = [a for a in envelope.reply_to if a is not None]
        content = Content(html="\n".join(html_parts) or None, text="\n".join(text_parts) or None)
        attachments = list(self.attachment_list)
        mailer_name = self.mailer_name

        class _Built(Mailable):
            def envelope(self) -> Envelope:
                return envelope

            def content(self) -> Content:
                return content

            def attachments(self) -> list[Attachment]:
                return attachments

        built = _Built()
        if mailer_name:
            built.mailer(mailer_name)
        return built


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
