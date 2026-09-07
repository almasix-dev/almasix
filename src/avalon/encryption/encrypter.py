"""Encrypter — JSON-safe encrypt/decrypt with previous-key rotation."""

from __future__ import annotations

import json
from typing import Any

from avalon.encryption.cipher import decrypt_string as _decrypt_string
from avalon.encryption.cipher import encrypt_string as _encrypt_string
from avalon.encryption.exceptions import DecryptException, EncryptException


def parse_previous_keys(raw: Any) -> list[str]:
    """Normalize ``APP_PREVIOUS_KEYS`` (comma-separated string or list)."""
    if raw is None or raw is False:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw).strip()
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def generate_key() -> str:
    """Return a new ``base64:…`` application key (32 random bytes)."""
    import base64
    import os

    return "base64:" + base64.b64encode(os.urandom(32)).decode("ascii")


class Encrypter:
    """Encrypt and decrypt values using ``APP_KEY`` (+ optional previous keys)."""

    def __init__(self, key: str, previous_keys: list[str] | None = None) -> None:
        self.key = key or "avalon-insecure-dev-key-change-me"
        self.previous_keys = list(previous_keys or [])

    @property
    def keys(self) -> list[str]:
        """Current key first, then previous keys (for decryption)."""
        seen: set[str] = set()
        ordered: list[str] = []
        for candidate in [self.key, *self.previous_keys]:
            if candidate and candidate not in seen:
                seen.add(candidate)
                ordered.append(candidate)
        return ordered

    def encrypt_string(self, value: str) -> str:
        return _encrypt_string(str(value), key=self.key)

    def decrypt_string(self, payload: str) -> str:
        for key in self.keys:
            plain = _decrypt_string(payload, key=key)
            if plain is not None:
                return plain
        raise DecryptException("The payload could not be decrypted.")

    def encrypt(self, value: Any) -> str:
        """Encrypt a JSON-serializable value (no pickle)."""
        try:
            serialized = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise EncryptException(
                "Value is not JSON-serializable. Use encrypt_string for raw text, "
                "or pass a JSON-safe structure."
            ) from exc
        return self.encrypt_string(serialized)

    def decrypt(self, payload: str) -> Any:
        """Decrypt a value produced by :meth:`encrypt`."""
        plain = self.decrypt_string(payload)
        try:
            return json.loads(plain)
        except json.JSONDecodeError as exc:
            raise DecryptException("The payload could not be deserialized.") from exc
