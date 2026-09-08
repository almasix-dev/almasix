"""Encryption errors."""

from __future__ import annotations


class EncryptException(Exception):
    """Raised when a value cannot be encrypted (e.g. non-JSON-safe payload)."""


class DecryptException(Exception):
    """Raised when a payload cannot be decrypted or was tampered with."""
