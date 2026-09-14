"""Vonage / Slack message builders."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VonageMessage:
    content_text: str = ""
    from_number: str | None = None
    unicode: bool = False
    client_reference: str | None = None

    def content(self, text: str) -> VonageMessage:
        self.content_text = text
        return self

    def from_(self, number: str) -> VonageMessage:
        self.from_number = number
        return self

    def unicode_(self, enabled: bool = True) -> VonageMessage:
        self.unicode = enabled
        return self

    def client_reference_(self, value: str) -> VonageMessage:
        self.client_reference = value
        return self

    def to_payload(self) -> dict[str, Any]:
        return {
            "text": self.content_text,
            "from": self.from_number,
            "unicode": self.unicode,
            "client_ref": self.client_reference,
        }


@dataclass
class SlackMessage:
    text: str = ""
    blocks: list[dict[str, Any]] = field(default_factory=list)
    channel: str | None = None

    def content(self, text: str) -> SlackMessage:
        self.text = text
        return self

    def header_block(self, text: str) -> SlackMessage:
        self.blocks.append(
            {"type": "header", "text": {"type": "plain_text", "text": text}}
        )
        return self

    def section_block(self, text: str) -> SlackMessage:
        self.blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": text}}
        )
        return self

    def to(self, channel: str) -> SlackMessage:
        self.channel = channel
        return self

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"text": self.text}
        if self.blocks:
            payload["blocks"] = self.blocks
        if self.channel:
            payload["channel"] = self.channel
        return payload
