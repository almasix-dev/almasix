"""Mailer manager, pending mail, and message building."""

from __future__ import annotations

import mimetypes
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from almasix.mail.mailable import (
    Address,
    Attachable,
    Attachment,
    EmbeddedImage,
    Mailable,
)
from almasix.mail.markdown import render_content
from almasix.mail.message import ResolvedAttachment, SentMessage
from almasix.mail.transport import Transport
from almasix.mail.transports.array import ArrayTransport
from almasix.mail.transports.composite import FailoverTransport, RoundRobinTransport
from almasix.mail.transports.log import LogTransport
from almasix.mail.transports.smtp import SmtpTransport


class MailManager:
    """Resolve named mailers from ``config/mail.py``."""

    def __init__(self, app: Any | None = None, config: dict[str, Any] | None = None) -> None:
        self.app = app
        self._config = config or {}
        self._mailers: dict[str, Mailer] = {}
        self._transports: dict[str, Any] = {}

    def set_config(self, config: dict[str, Any]) -> None:
        self._config = config
        self._mailers.clear()
        self._transports.clear()

    def get_default_mailer(self) -> str:
        return str(self._config.get("default") or "log")

    def set_default_mailer(self, name: str) -> None:
        """Send through this mailer from here on (`Mail::fake()` uses it)."""
        self._config = {**self._config, "default": name}

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

    def _resolve_transport(self, name: str) -> Any:
        if name in self._transports:
            return self._transports[name]
        cfg = self._mailer_config(name)
        driver = str(cfg.get("transport") or cfg.get("driver") or "log")
        transport: Any
        if driver == "array":
            transport = ArrayTransport()
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
        elif driver == "failover":
            transport = FailoverTransport(
                self._resolve_transport,
                list(cfg.get("mailers") or []),
                retry_after=int(cfg.get("retry_after") or 60),
            )
        elif driver in {"roundrobin", "round_robin"}:
            transport = RoundRobinTransport(
                self._resolve_transport,
                list(cfg.get("mailers") or []),
            )
        elif driver == "mailgun":
            from almasix.mail.transports.mailgun import MailgunTransport

            transport = MailgunTransport.from_config(cfg, self._services())
        elif driver == "postmark":
            from almasix.mail.transports.postmark import PostmarkTransport

            transport = PostmarkTransport.from_config(cfg, self._services())
        elif driver == "resend":
            from almasix.mail.transports.resend import ResendTransport

            transport = ResendTransport.from_config(cfg, self._services())
        elif driver == "ses":
            from almasix.mail.transports.ses import SesTransport

            transport = SesTransport.from_config(cfg, self._services())
        elif driver == "cloudflare":
            from almasix.mail.transports.cloudflare import CloudflareTransport

            transport = CloudflareTransport.from_config(cfg, self._services())
        elif driver == "sendmail":
            from almasix.mail.transports.sendmail import SendmailTransport

            transport = SendmailTransport(path=str(cfg.get("path") or "/usr/sbin/sendmail -bs"))
        else:
            raise ValueError(f"Unsupported mail transport: {driver!r}")
        self._transports[name] = transport
        return transport

    def _services(self) -> dict[str, Any]:
        if isinstance(self._config.get("services"), dict):
            return dict(self._config["services"])
        if self.app is None:
            return {}
        try:
            return dict(self.app.config.get("services") or {})
        except Exception:
            return {}

    def default_from(self) -> Address | None:
        from_cfg = self._config.get("from") or {}
        address = from_cfg.get("address")
        if not address:
            return None
        return Address(str(address), from_cfg.get("name"))

    def always_to(self) -> list[Address]:
        raw = self._config.get("to") or self._config.get("always")
        if not raw:
            return []
        if isinstance(raw, dict):
            address = raw.get("address")
            if not address:
                return []
            return [Address(str(address), raw.get("name"))]
        return Address.parse_many(raw)


class Mailer:
    """Send or queue mailables through a configured transport."""

    def __init__(
        self,
        name: str,
        transport: Transport | ArrayTransport | Any,
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

    def later(
        self,
        delay: int | float | timedelta | datetime,
        mailable: Mailable,
        *,
        to: list[Address] | None = None,
    ) -> SentMessage | None:
        pending = PendingMail(self)
        if to:
            pending._to = list(to)
        return pending.later(delay, mailable)


class PendingMail:
    """Fluent recipient builder: ``Mail.to(...).cc(...).send(mailable)``."""

    def __init__(self, mailer: Mailer) -> None:
        self._mailer = mailer
        self._to: list[Address] = []
        self._cc: list[Address] = []
        self._bcc: list[Address] = []

    def to(self, *addresses: str | Address | tuple[str, str | None]) -> PendingMail:
        if addresses:
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

        if isinstance(mailable, ShouldQueue) or (
            getattr(mailable, "queue", False) is True
            or (isinstance(getattr(mailable, "queue", None), str) and mailable.queue)
        ):
            return self.queue(mailable)
        return self._deliver(mailable, queued=False)

    def queue(self, mailable: Mailable) -> SentMessage | None:
        return self._deliver(mailable, queued=True)

    def later(
        self,
        delay: int | float | timedelta | datetime,
        mailable: Mailable,
    ) -> SentMessage | None:
        seconds = _delay_seconds(delay)
        return self._deliver(mailable, queued=True, delay=seconds)

    def _deliver(
        self,
        mailable: Mailable,
        *,
        queued: bool,
        delay: float = 0,
    ) -> SentMessage | None:
        locale_token = _push_locale(mailable)
        try:
            message = self._build_message(mailable)
            if not _fire_sending(message):
                return None
            transport = self._mailer.transport
            if queued:
                if isinstance(transport, ArrayTransport):
                    transport.queue(message)
                    _fire_sent(message)
                    return message
                if _dispatch_to_queue(self._mailer, message, delay, mailable):
                    return message
            transport.send(message)
            _fire_sent(message)
            return message
        finally:
            _pop_locale(locale_token)

    def _build_message(self, mailable: Mailable) -> SentMessage:
        envelope = mailable.envelope()
        content = mailable.content()
        html_body, text_body = render_content(content)
        from_address = envelope.from_address or self._mailer.manager.default_from()
        always = self._mailer.manager.always_to()
        to = list(always) if always else list(self._to)
        cc = [] if always else list(self._cc)
        bcc = [] if always else list(self._bcc)
        embeds = list(mailable.embeds())
        message = SentMessage(
            mailable=mailable,
            to=to,
            cc=cc,
            bcc=bcc,
            subject=envelope.subject,
            html=html_body,
            text=text_body,
            from_address=from_address,
            reply_to=list(envelope.reply_to),
            attachments=_resolve_attachments(mailable.attachments(), self._mailer.manager.app),
            embeds=embeds,
            tags=list(envelope.tags),
            metadata=dict(envelope.metadata),
            headers=dict(envelope.headers),
        )
        hook = getattr(mailable, "with_message", None)
        if callable(hook):
            hook(message)
        return message


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
        name = getattr(mailable, "mailer_name", None)
        return cls.mailer(name).send(mailable)

    @classmethod
    def queue(cls, mailable: Mailable) -> SentMessage | None:
        name = getattr(mailable, "mailer_name", None)
        return cls.mailer(name).queue(mailable)

    @classmethod
    def later(
        cls,
        delay: int | float | timedelta | datetime,
        mailable: Mailable,
    ) -> SentMessage | None:
        name = getattr(mailable, "mailer_name", None)
        return cls.mailer(name).later(delay, mailable)

    @classmethod
    def fake(cls, name: str = "array") -> Any:
        """Send to an array instead of anywhere (Laravel ``Mail::fake()``).

        Returns the assertions — ``Mail.fake().assert_sent(WelcomeMail)`` —
        and configures the mailer if the application has not.
        """
        from almasix.mail.testing import MailAssertions

        manager = cls.manager()
        mailers = dict(manager._config.get("mailers") or {})
        if name not in mailers:
            mailers[name] = {"transport": "array"}
            manager.set_config({**manager._config, "mailers": mailers})
        manager.set_default_mailer(name)
        assertions = MailAssertions(name)
        assertions.flush()
        return assertions


def _resolve_attachments(
    attachments: list[Attachment | Attachable | Any],
    app: Any | None,
) -> list[ResolvedAttachment]:
    resolved: list[ResolvedAttachment] = []
    for item in attachments:
        attachment: Attachment
        if isinstance(item, Attachment):
            attachment = item
        elif isinstance(item, Attachable):
            attachment = item.to_mail_attachment()
        elif hasattr(item, "to_mail_attachment"):
            attachment = item.to_mail_attachment()
        else:
            raise TypeError(f"Unsupported attachment type: {type(item)!r}")

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


def _dispatch_to_queue(
    mailer: Mailer,
    message: SentMessage,
    delay: float = 0,
    mailable: Mailable | None = None,
) -> bool:
    """Push a serializable mail job. Returns True when queued successfully."""
    try:
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        from almasix.mail.jobs import SendQueuedMailable
        from almasix.queue.helpers import dispatch
    except ImportError:
        return False

    job = SendQueuedMailable.from_sent_message(mailer.name, message)
    if mailable is not None:
        queue_name = getattr(mailable, "queue", None)
        if isinstance(queue_name, str) and queue_name:
            job.queue = queue_name
        connection = getattr(mailable, "connection", None)
        if connection:
            job.connection = connection  # type: ignore[attr-defined]
    if delay:
        job.delay = delay  # type: ignore[attr-defined]

    async def _push() -> Any:
        return await dispatch(job)

    try:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(_push())
            return True
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(lambda: asyncio.run(_push())).result()
        return True
    except Exception:
        return False


def _delay_seconds(delay: int | float | timedelta | datetime) -> float:
    if isinstance(delay, datetime):
        return max(0.0, (delay - datetime.now(delay.tzinfo)).total_seconds())
    if isinstance(delay, timedelta):
        return max(0.0, delay.total_seconds())
    return max(0.0, float(delay))


def _push_locale(mailable: Mailable) -> Any:
    locale = getattr(mailable, "locale", None)
    if not locale:
        return None
    from almasix.translation.locale import get_locale, set_locale

    previous = get_locale()
    set_locale(locale)
    return previous


def _pop_locale(previous: Any) -> None:
    if previous is None:
        return
    from almasix.translation.locale import set_locale

    set_locale(previous)


def _fire_sending(message: SentMessage) -> bool:
    try:
        from almasix.events.helpers import get_dispatcher
        from almasix.mail.events import MessageSending

        result = get_dispatcher().dispatch(MessageSending(message=message), halt=True)
        if result is False:
            return False
    except Exception:
        pass
    return True


def _fire_sent(message: SentMessage) -> None:
    try:
        from almasix.events.helpers import get_dispatcher
        from almasix.mail.events import MessageSent

        get_dispatcher().dispatch(MessageSent(message=message))
    except Exception:
        pass


Callback = Callable[[SentMessage], None]

# Re-export for type checkers that look for embeds on build path
_ = EmbeddedImage
