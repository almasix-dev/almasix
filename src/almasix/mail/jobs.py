"""Serializable queued mailable delivery."""

from __future__ import annotations

import base64
from typing import Any

from almasix.mail.mailable import Address
from almasix.mail.message import ResolvedAttachment, SentMessage
from almasix.queue.job import Job, ShouldQueue


class SendQueuedMailable(ShouldQueue, Job):
    """Deliver a pre-built message payload from the queue worker."""

    queue = "default"

    def __init__(
        self,
        *,
        mailer_name: str = "smtp",
        to: list[dict[str, Any]] | None = None,
        cc: list[dict[str, Any]] | None = None,
        bcc: list[dict[str, Any]] | None = None,
        subject: str = "",
        html: str | None = None,
        text: str | None = None,
        from_address: dict[str, Any] | None = None,
        reply_to: list[dict[str, Any]] | None = None,
        attachments: list[dict[str, Any]] | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        mailable_class: str | None = None,
    ) -> None:
        self.mailer_name = mailer_name
        self.to = to or []
        self.cc = cc or []
        self.bcc = bcc or []
        self.subject = subject
        self.html = html
        self.text = text
        self.from_address = from_address
        self.reply_to = reply_to or []
        self.attachments = attachments or []
        self.tags = tags or []
        self.metadata = metadata or {}
        self.mailable_class = mailable_class

    @classmethod
    def from_sent_message(cls, mailer_name: str, message: SentMessage) -> SendQueuedMailable:
        def addr(value: Address | None) -> dict[str, Any] | None:
            if value is None:
                return None
            return {"address": value.address, "name": value.name}

        def addrs(values: list[Address]) -> list[dict[str, Any]]:
            return [a for a in (addr(v) for v in values) if a is not None]

        attachments = [
            {
                "name": item.name,
                "data": base64.b64encode(item.data).decode("ascii"),
                "mime": item.mime,
            }
            for item in message.attachments
        ]
        mailable_class = None
        if message.mailable is not None:
            mailable_class = (
                f"{type(message.mailable).__module__}.{type(message.mailable).__qualname__}"
            )
        return cls(
            mailer_name=mailer_name,
            to=addrs(message.to),
            cc=addrs(message.cc),
            bcc=addrs(message.bcc),
            subject=message.subject,
            html=message.html,
            text=message.text,
            from_address=addr(message.from_address),
            reply_to=addrs(message.reply_to),
            attachments=attachments,
            tags=list(message.tags),
            metadata=dict(message.metadata),
            mailable_class=mailable_class,
        )

    def handle(self) -> None:
        from almasix.mail.mailer import Mail

        message = self.to_sent_message()
        Mail.manager().mailer(self.mailer_name).transport.send(message)

    def to_sent_message(self) -> SentMessage:
        def parse(raw: dict[str, Any] | None) -> Address | None:
            if not raw:
                return None
            return Address(str(raw["address"]), raw.get("name"))

        attachments = [
            ResolvedAttachment(
                name=str(item["name"]),
                data=base64.b64decode(item["data"]),
                mime=item.get("mime"),
            )
            for item in self.attachments
        ]
        # Lightweight stub so array assertions can match by class name after workers run.
        mailable = None
        if self.mailable_class:
            name = self.mailable_class.rsplit(".", 1)[-1]
            mailable = type(name, (), {})()
        return SentMessage(
            mailable=mailable,
            to=[a for a in (parse(v) for v in self.to) if a is not None],
            cc=[a for a in (parse(v) for v in self.cc) if a is not None],
            bcc=[a for a in (parse(v) for v in self.bcc) if a is not None],
            subject=self.subject,
            html=self.html,
            text=self.text,
            from_address=parse(self.from_address),
            reply_to=[a for a in (parse(v) for v in self.reply_to) if a is not None],
            attachments=attachments,
            tags=list(self.tags),
            metadata=dict(self.metadata),
        )
