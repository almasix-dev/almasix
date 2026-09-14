"""Shared helpers for HTTP-based ESP mail transports."""

from __future__ import annotations

from typing import Any

from almasix.mail.message import SentMessage


def message_payload(message: SentMessage) -> dict[str, Any]:
    """Common JSON-ish view of a SentMessage for HTTP APIs."""
    return {
        "from": _addr(message.from_address),
        "to": [_addr(a) for a in message.to],
        "cc": [_addr(a) for a in message.cc],
        "bcc": [_addr(a) for a in message.bcc],
        "subject": message.subject,
        "html": message.html,
        "text": message.text,
        "tags": list(message.tags),
        "metadata": dict(message.metadata),
        "headers": dict(message.headers),
        "attachments": [
            {"name": a.name, "mime": a.mime, "size": len(a.data)} for a in message.attachments
        ],
    }


def _addr(address: Any) -> dict[str, str | None] | None:
    if address is None:
        return None
    return {"email": address.address, "name": address.name}


def services_section(services: dict[str, Any], key: str) -> dict[str, Any]:
    section = services.get(key) or {}
    return dict(section) if isinstance(section, dict) else {}
