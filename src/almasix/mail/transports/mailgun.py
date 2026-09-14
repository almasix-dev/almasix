"""Mailgun HTTP transport."""

from __future__ import annotations

from typing import Any

from almasix.mail.message import SentMessage
from almasix.mail.transports.http_base import message_payload, response_status, services_section


class MailgunTransport:
    def __init__(
        self,
        *,
        domain: str,
        secret: str,
        endpoint: str = "api.mailgun.net",
        scheme: str = "https",
    ) -> None:
        self.domain = domain
        self.secret = secret
        self.endpoint = endpoint
        self.scheme = scheme

    @classmethod
    def from_config(cls, cfg: dict[str, Any], services: dict[str, Any]) -> MailgunTransport:
        svc = services_section(services, "mailgun")
        return cls(
            domain=str(cfg.get("domain") or svc.get("domain") or ""),
            secret=str(cfg.get("secret") or svc.get("secret") or ""),
            endpoint=str(cfg.get("endpoint") or svc.get("endpoint") or "api.mailgun.net"),
            scheme=str(cfg.get("scheme") or svc.get("scheme") or "https"),
        )

    def send(self, message: SentMessage) -> None:
        from almasix.client import Http

        url = f"{self.scheme}://{self.endpoint}/v3/{self.domain}/messages"
        payload = message_payload(message)
        data = {
            "from": _format_from(message),
            "to": [a.address for a in message.to],
            "subject": message.subject,
            "text": message.text or "",
            "html": message.html or "",
        }
        if message.cc:
            data["cc"] = [a.address for a in message.cc]
        if message.bcc:
            data["bcc"] = [a.address for a in message.bcc]
        for tag in message.tags:
            data.setdefault("o:tag", [])
            if isinstance(data["o:tag"], list):
                data["o:tag"].append(tag)
        for key, value in message.metadata.items():
            data[f"v:{key}"] = value
        response = Http.as_form().with_basic_auth("api", self.secret).post(url, data)
        if hasattr(response, "successful") and not response.successful():
            raise RuntimeError(f"Mailgun send failed: {response_status(response)}")
        # Keep payload reference for fakes/debugging
        message.metadata.setdefault("_mailgun", payload)


def _format_from(message: SentMessage) -> str:
    if message.from_address is None:
        return ""
    if message.from_address.name:
        return f"{message.from_address.name} <{message.from_address.address}>"
    return message.from_address.address
