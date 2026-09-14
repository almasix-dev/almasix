"""Amazon SES HTTP transport (simple SendEmail-shaped POST for fakes / HTTP clients)."""

from __future__ import annotations

from typing import Any

from almasix.mail.message import SentMessage
from almasix.mail.transports.http_base import message_payload, response_status, services_section


class SesTransport:
    """SES via HTTP. CI uses Http.fake(); production may point at AWS endpoint."""

    def __init__(
        self,
        *,
        key: str | None = None,
        secret: str | None = None,
        region: str = "us-east-1",
        endpoint: str | None = None,
    ) -> None:
        self.key = key
        self.secret = secret
        self.region = region
        self.endpoint = endpoint or f"https://email.{region}.amazonaws.com"

    @classmethod
    def from_config(cls, cfg: dict[str, Any], services: dict[str, Any]) -> SesTransport:
        svc = services_section(services, "ses")
        return cls(
            key=cfg.get("key") or svc.get("key"),
            secret=cfg.get("secret") or svc.get("secret"),
            region=str(cfg.get("region") or svc.get("region") or "us-east-1"),
        )

    def send(self, message: SentMessage) -> None:
        from almasix.client import Http

        # Simplified JSON body — enough for fakes and gateway proxies.
        body = {
            "Action": "SendEmail",
            "Source": message.from_address.address if message.from_address else "",
            "Destination": {
                "ToAddresses": [a.address for a in message.to],
                "CcAddresses": [a.address for a in message.cc],
                "BccAddresses": [a.address for a in message.bcc],
            },
            "Message": {
                "Subject": {"Data": message.subject},
                "Body": {
                    "Html": {"Data": message.html or ""},
                    "Text": {"Data": message.text or ""},
                },
            },
            "Tags": [{"Name": k, "Value": str(v)} for k, v in message.metadata.items()],
        }
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["X-Amz-Access-Key"] = str(self.key)
        response = Http.with_headers(headers).post(self.endpoint, body)
        if hasattr(response, "successful") and not response.successful():
            raise RuntimeError(f"SES send failed: {response_status(response)}")
        message.metadata.setdefault("_ses", message_payload(message))
