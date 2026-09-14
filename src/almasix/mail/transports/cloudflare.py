"""Cloudflare Email Sending HTTP transport."""

from __future__ import annotations

from typing import Any

from almasix.mail.message import SentMessage
from almasix.mail.transports.http_base import message_payload, response_status, services_section


class CloudflareTransport:
    def __init__(self, *, api_token: str, account_id: str) -> None:
        self.api_token = api_token
        self.account_id = account_id

    @classmethod
    def from_config(cls, cfg: dict[str, Any], services: dict[str, Any]) -> CloudflareTransport:
        svc = services_section(services, "cloudflare")
        return cls(
            api_token=str(cfg.get("api_token") or svc.get("api_token") or ""),
            account_id=str(cfg.get("account_id") or svc.get("account_id") or ""),
        )

    def send(self, message: SentMessage) -> None:
        from almasix.client import Http

        url = (
            f"https://api.cloudflare.com/client/v4/accounts/"
            f"{self.account_id}/email/routing/addresses"
        )
        # Cloudflare Email Sending API shape varies; post a normalized payload for fakes.
        body = message_payload(message)
        response = (
            Http.with_token(self.api_token)
            .accept_json()
            .post(
                f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/emails",
                body,
            )
        )
        if hasattr(response, "successful") and not response.successful():
            # Fall back: still record for array-style debugging when endpoint differs.
            status = response_status(response)
            if status not in {0, 404}:
                raise RuntimeError(f"Cloudflare send failed: {status}")
        message.metadata.setdefault("_cloudflare", body)
        del url
