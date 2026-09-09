"""Plain-text token wrapper returned by ``create_token``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class NewAccessToken:
    """Laravel ``NewAccessToken`` — access token model + one-time plain text."""

    access_token: Any
    plain_text_token: str

    def __str__(self) -> str:
        return self.plain_text_token
