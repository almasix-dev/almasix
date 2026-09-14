"""Mailable message types — Laravel 9+ envelope/content/attachments shape."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class Address:
    """Email address with optional display name."""

    address: str
    name: str | None = None

    @classmethod
    def parse(cls, value: str | Address | tuple[str, str | None] | None) -> Address | None:
        if value is None:
            return None
        if isinstance(value, Address):
            return value
        if isinstance(value, tuple):
            addr, name = value
            return cls(str(addr), str(name) if name else None)
        text = str(value).strip()
        if not text:
            return None
        if "<" in text and text.endswith(">"):
            name, _, rest = text.partition("<")
            return cls(rest.rstrip(">").strip(), name.strip().strip('"') or None)
        return cls(text)

    @classmethod
    def parse_many(
        cls,
        *values: str | Address | tuple[str, str | None] | list[Any],
    ) -> list[Address]:
        out: list[Address] = []
        for value in values:
            if isinstance(value, list):
                out.extend(cls.parse_many(*value))
                continue
            parsed = cls.parse(value)  # type: ignore[arg-type]
            if parsed is not None:
                out.append(parsed)
        return out


@dataclass
class Envelope:
    """Message envelope metadata."""

    subject: str = ""
    from_address: Address | None = None
    reply_to: list[Address] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class Content:
    """Message body — HTML, plain text, or Prism/Markdown view names."""

    html: str | None = None
    text: str | None = None
    markdown: str | None = None
    view: str | None = None
    with_data: dict[str, Any] = field(default_factory=dict)
    theme: str | None = None  # Prism layout, default mail.themes.default


@dataclass
class EmbeddedImage:
    """Inline CID attachment referenced from HTML as ``cid:<content_id>``."""

    content_id: str
    data: bytes
    mime: str | None = None
    name: str | None = None


@dataclass
class Attachment:
    """Outgoing attachment from path, storage disk, raw bytes, or Attachable."""

    path: str | None = None
    data: bytes | None = None
    name: str | None = None
    mime: str | None = None
    disk: str | None = None
    storage_path: str | None = None

    @classmethod
    def from_path(
        cls,
        path: str,
        *,
        name: str | None = None,
        mime: str | None = None,
    ) -> Attachment:
        return cls(path=path, name=name, mime=mime)

    @classmethod
    def from_storage(
        cls,
        path: str,
        *,
        disk: str | None = None,
        name: str | None = None,
        mime: str | None = None,
    ) -> Attachment:
        return cls(storage_path=path, disk=disk, name=name, mime=mime)

    @classmethod
    def from_data(
        cls,
        data: bytes,
        name: str,
        *,
        mime: str | None = None,
    ) -> Attachment:
        return cls(data=data, name=name, mime=mime)

    @classmethod
    def from_attachable(cls, attachable: Attachable) -> Attachment:
        return attachable.to_mail_attachment()


@runtime_checkable
class Attachable(Protocol):
    """Objects that can become a mail attachment (Laravel ``Attachable``)."""

    def to_mail_attachment(self) -> Attachment: ...


class ShouldQueue:
    """Marker for mailables that prefer queued delivery."""


class Mailable:
    """Base class for class-based mail messages."""

    queue: str | bool = False
    connection: str | None = None
    locale: str | None = None
    mailer_name: str | None = None

    def envelope(self) -> Envelope:
        return Envelope()

    def content(self) -> Content:
        return Content()

    def attachments(self) -> list[Attachment | Attachable]:
        return []

    def embeds(self) -> list[EmbeddedImage]:
        return []

    def with_message(self, message: Any) -> None:
        """Hook to mutate the transport-level message before send (Laravel ``withSymfonyMessage``)."""

    def set_locale(self, locale: str) -> Mailable:
        self.locale = locale
        return self

    def on_queue(self, queue: str) -> Mailable:
        self.queue = queue
        return self

    def on_connection(self, connection: str) -> Mailable:
        self.connection = connection
        return self

    def mailer(self, name: str) -> Mailable:
        self.mailer_name = name
        return self

    def render(self) -> str:
        """Render HTML (or text fallback) without sending — browser preview helper."""
        from almasix.mail.markdown import render_content

        html_body, text_body = render_content(self.content())
        return html_body or text_body or ""
