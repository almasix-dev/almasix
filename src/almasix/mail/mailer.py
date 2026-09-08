"""Mailer manager, pending mail, and message building."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, Callable

from almasix.mail.mailable import Address, Attachment, Mailable
from almasix.mail.markdown import render_content
from almasix.mail.message import ResolvedAttachment, SentMessage
from almasix.mail.transport import Transport
from almasix.mail.transports.array import ArrayTransport
from almasix.mail.transports.log import LogTransport
from almasix.mail.transports.smtp import SmtpTransport


class MailManager:
    """Resolve named mailers from ``config/mail.py``."""

    def __init__(self, app: Any | None = None, config: dict[str, Any] | None = None) -> None:
        self.app = app
        self._config = config or {}
        self._mailers: dict[str, Mailer] = {}
        self._transports: dict[str, Transport | ArrayTransport] = {}

    def set_config(self, config: dict[str, Any]) -> None:
        self._config = config
        self._mailers.clear()
        self._transports.clear()

    def get_default_mailer(self) -> str:
        return str(self._config.get("default") or "log")

    def mailer(self, name: str | None = None) -> Mailer:
        key = name or self.get_default_mailer()
        if key not in self._mailers:
            self._mailers[key] = Mailer(key, self._resolve_transport(key), self)
        return self._mailers[key]

    def array_transport(self, name: str = "array") -> ArrayTransport | None:
        transport = self._resolve_transport(name)
        return transport if isinstance(transport, ArrayTransport) else None

    def _mailer_config(self, name: str) -> dict[str, Any]:
        mailers = self._config.get("mailers") or {}
        cfg = mailers.get(name)
        if cfg is None:
            raise KeyError(f"Mailer [{name}] is not configured.")
        return dict(cfg)

    def _resolve_transport(self, name: str) -> Transport | ArrayTransport:
        if name in self._transports:
            return self._transports[name]
        cfg = self._mailer_config(name)
        driver = str(cfg.get("transport") or cfg.get("driver") or "log")
        if driver == "array":
            transport: Transport | ArrayTransport = ArrayTransport()
        elif driver == "log":
            transport = LogTransport(channel=cfg.get("channel"))
        elif driver == "smtp":
            transport = SmtpTransport(
                host=str(cfg.get("host") or "127.0.0.1"),
                port=int(cfg.get("port") or 2525),
                username=cfg.get("username"),
                password=cfg.get("password"),
                encryption=cfg.get("encryption"),
                timeout=cfg.get("timeout"),
                local_domain=cfg.get("local_domain"),
                client=cfg.get("client"),
            )
        else:
            raise ValueError(f"Unsupported mail transport: {driver!r}")
        self._transports[name] = transport
        return transport

    def default_from(self) -> Address | None:
        from_cfg = self._config.get("from") or {}
        address = from_cfg.get("address")
        if not address:
            return None
        return Address(str(address), from_cfg.get("name"))


class Mailer:
    """Send or queue mailables through a configured transport."""

    def __init__(
        self,
        name: str,
        transport: Transport | ArrayTransport,
        manager: MailManager,
    ) -> None:
        self.name = name
        self.transport = transport
        self.manager = manager

    def to(self, *addresses: str | Address | tuple[str, str | None]) -> PendingMail:
        return PendingMail(self).to(*addresses)

    def send(self, mailable: Mailable, *, to: list[Address] | None = None) -> SentMessage | None:
        pending = PendingMail(self)
        if to:
            pending._to = list(to)
        return pending.send(mailable)

    def queue(self, mailable: Mailable, *, to: list[Address] | None = None) -> SentMessage | None:
        pending = PendingMail(self)
        if to:
            pending._to = list(to)
        return pending.queue(mailable)


class PendingMail:
    """Fluent recipient builder: ``Mail.to(...).cc(...).send(mailable)``."""

    def __init__(self, mailer: Mailer) -> None:
        self._mailer = mailer
        self._to: list[Address] = []
        self._cc: list[Address] = []
        self._bcc: list[Address] = []

    def to(self, *addresses: str | Address | tuple[str, str | None]) -> PendingMail:
        self._to.extend(Address.parse_many(*addresses))
        return self

    def cc(self, *addresses: str | Address | tuple[str, str | None]) -> PendingMail:
        self._cc.extend(Address.parse_many(*addresses))
        return self

    def bcc(self, *addresses: str | Address | tuple[str, str | None]) -> PendingMail:
        self._bcc.extend(Address.parse_many(*addresses))
        return self

    def send(self, mailable: Mailable) -> SentMessage | None:
        from almasix.mail.mailable import ShouldQueue

        if isinstance(mailable, ShouldQueue):
            return self.queue(mailable)
        message = self._build_message(mailable)
        self._mailer.transport.send(message)
        return message

    def queue(self, mailable: Mailable) -> SentMessage | None:
        message = self._build_message(mailable)
        transport = self._mailer.transport
        # Array transport is the test fake — record as queued only (Laravel Mail::fake).
        if isinstance(transport, ArrayTransport):
            transport.queue(message)
            return message
        if _dispatch_to_queue(self._mailer, message):
            return message
        self._mailer.transport.send(message)
        return message

    def _build_message(self, mailable: Mailable) -> SentMessage:
        envelope = mailable.envelope()
        content = mailable.content()
        html_body, text_body = render_content(content)
        from_address = envelope.from_address or self._mailer.manager.default_from()
        return SentMessage(
            mailable=mailable,
            to=list(self._to),
            cc=list(self._cc),
            bcc=list(self._bcc),
            subject=envelope.subject,
            html=html_body,
            text=text_body,
            from_address=from_address,
            reply_to=list(envelope.reply_to),
            attachments=_resolve_attachments(mailable.attachments(), self._mailer.manager.app),
            tags=list(envelope.tags),
            metadata=dict(envelope.metadata),
        )


class Mail:
    """Static-style façade: ``Mail.to(...).send(mailable)``."""

    _manager: MailManager | None = None

    @classmethod
    def set_manager(cls, manager: MailManager | None) -> None:
        cls._manager = manager

    @classmethod
    def manager(cls) -> MailManager:
        if cls._manager is None:
            cls._manager = MailManager()
        return cls._manager

    @classmethod
    def mailer(cls, name: str | None = None) -> Mailer:
        return cls.manager().mailer(name)

    @classmethod
    def to(cls, *addresses: str | Address | tuple[str, str | None]) -> PendingMail:
        return cls.mailer().to(*addresses)

    @classmethod
    def send(cls, mailable: Mailable) -> SentMessage | None:
        return cls.mailer().send(mailable)

    @classmethod
    def queue(cls, mailable: Mailable) -> SentMessage | None:
        return cls.mailer().queue(mailable)


def _resolve_attachments(
    attachments: list[Attachment],
    app: Any | None,
) -> list[ResolvedAttachment]:
    resolved: list[ResolvedAttachment] = []
    for attachment in attachments:
        name = attachment.name
        data = attachment.data
        mime = attachment.mime

        if attachment.path is not None:
            path = Path(attachment.path)
            if not path.is_absolute() and app is not None:
                path = Path(app.base_path) / path
            data = path.read_bytes()
            name = name or path.name
            mime = mime or mimetypes.guess_type(path.name)[0]
        elif attachment.storage_path is not None:
            data = _read_storage(attachment.disk, attachment.storage_path)
            name = name or Path(attachment.storage_path).name
            mime = mime or mimetypes.guess_type(name or "")[0]
        elif data is None:
            raise ValueError("Attachment requires path, storage_path, or data.")

        if not name:
            raise ValueError("Attachment requires a file name.")
        resolved.append(ResolvedAttachment(name=name, data=data, mime=mime))
    return resolved


def _read_storage(disk: str | None, path: str) -> bytes:
    try:
        from almasix.filesystem.helpers import storage

        return storage(disk).get(path)
    except Exception as exc:
        raise RuntimeError(f"Unable to read attachment from storage disk: {path!r}") from exc


def _dispatch_to_queue(mailer: Mailer, message: SentMessage) -> bool:
    """Push a serializable mail job. Returns True when queued successfully."""
    try:
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        from almasix.mail.jobs import SendQueuedMailable
        from almasix.queue.helpers import dispatch
    except ImportError:
        return False

    job = SendQueuedMailable.from_sent_message(mailer.name, message)

    async def _push() -> Any:
        return await dispatch(job)

    try:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(_push())
            return True
        # Sync façade called from async context — push on a side loop.
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(lambda: asyncio.run(_push())).result()
        return True
    except Exception:
        return False


Callback = Callable[[SentMessage], None]
