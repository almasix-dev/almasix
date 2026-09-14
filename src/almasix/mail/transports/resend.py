"""Resend HTTP transport."""

from __future__ import annotations

from typing import Any

from almasix.mail.message import SentMessage
from almasix.mail.transports.http_base import message_payload, services_section


class ResendTransport:
    def __init__(self, *, key: str) -> None:
        self.key = key

    @classmethod
    def from_config(cls, cfg: dict[str, Any], services: dict[str, Any]) -> ResendTransport:
        svc = services_section(services, "resend")
        return cls(key=str(cfg.get("key") or svc.get("key") or ""))

    def send(self, message: SentMessage) -> None:
        from almasix.client import Http

        body: dict[str, Any] = {
            "from": _format_from(message),
            "to": [a.address for a in message.to],
            "subject": message.subject,
        }
        if message.html:
            body["html"] = message.html
        if message.text:
            body["text"] = message.text
        if message.cc:
            body["cc"] = [a.address for a in message.cc]
        if message.bcc:
            body["bcc"] = [a.address for a in message.bcc]
        if message.tags:
            body["tags"] = [{"name": t} for t in message.tags]
        response = (
            Http.with_token(self.key)
            .accept_json()
            .post("https://api.resend.com/emails", body)
        )
        if hasattr(response, "successful") and not response.successful():
            raise RuntimeError(f"Resend send failed: {getattr(response, 'status', '?')}")
        message.metadata.setdefault("_resend", message_payload(message))


def _format_from(message: SentMessage) -> str:
    if message.from_address is None:
        return ""
    if message.from_address.name:
        return f"{message.from_address.name} <{message.from_address.address}>"
    return message.from_address.address
