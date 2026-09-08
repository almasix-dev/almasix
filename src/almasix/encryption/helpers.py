"""Functional helpers: ``encrypt`` / ``decrypt`` / ``encrypt_string`` / ``decrypt_string``."""

from __future__ import annotations

from typing import Any

from almasix.encryption.encrypter import Encrypter, parse_previous_keys
from almasix.encryption.facade import Crypt


def resolve_encrypter() -> Encrypter:
    """Build an :class:`Encrypter` from ``config('app')`` (or secure defaults)."""
    try:
        from almasix.config import config

        key = str(config("app.key", "") or "") or "almasix-insecure-dev-key-change-me"
        previous = parse_previous_keys(config("app.previous_keys", []))
    except Exception:  # noqa: BLE001 — config may be unavailable before boot
        key = "almasix-insecure-dev-key-change-me"
        previous = []
    return Encrypter(key, previous)


def get_encrypter() -> Encrypter:
    return Crypt.get_encrypter()


def encrypt(value: Any) -> str:
    return Crypt.encrypt(value)


def decrypt(payload: str) -> Any:
    return Crypt.decrypt(payload)


def encrypt_string(value: str) -> str:
    return Crypt.encrypt_string(value)


def decrypt_string(payload: str) -> str:
    return Crypt.decrypt_string(payload)
