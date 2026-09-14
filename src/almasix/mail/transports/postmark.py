"""Postmark HTTP transport."""

from __future__ import annotations

from typing import Any

from almasix.mail.message import SentMessage
from almasix.mail.transports.http_base import message_payload, response_status, services_section


class PostmarkTransport:
    def __init__(self, *, token: str) -> None:
        self.token = token

    @classmethod
    def from_config(cls, cfg: dict[str, Any], services: dict[str, Any]) -> PostmarkTransport:
        svc = services_section(services, "postmark")
        return cls(token=str(cfg.get("token") or svc.get("token") or ""))

    def send(self, message: SentMessage) -> None:
        from almasix.client import Http

        body = {
            "From": _format_from(message),
            "To": ", ".join(a.address for a in message.to),
            "Subject": message.subject,
            "HtmlBody": message.html or "",
            "TextBody": message.text or "",
            "Tag": message.tags[0] if message.tags else None,
            "Metadata": message.metadata or None,
        }
        if message.cc:
            body["Cc"] = ", ".join(a.address for a in message.cc)
        if message.bcc:
            body["Bcc"] = ", ".join(a.address for a in message.bcc)
        response = Http.with_headers(
            {
                "X-Postmark-Server-Token": self.token,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        ).post("https://api.postmarkapp.com/email", body)
        if hasattr(response, "successful") and not response.successful():
            raise RuntimeError(f"Postmark send failed: {response_status(response)}")
        message.metadata.setdefault("_postmark", message_payload(message))


def _format_from(message: SentMessage) -> str:
    if message.from_address is None:
        return ""
    if message.from_address.name:
        return f"{message.from_address.name} <{message.from_address.address}>"
    return message.from_address.address
