"""Authenticated stream cipher shared by Crypt and cookie encryption."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hashlib.sha256(key + nonce + counter.to_bytes(4, "big")).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def encrypt_string(value: str, *, key: str) -> str:
    """Return ``nonce.ciphertext.mac`` (url-safe base64 segments)."""
    raw_key = hashlib.sha256(key.encode("utf-8")).digest()
    nonce = os.urandom(16)
    plain = value.encode("utf-8")
    cipher = bytes(a ^ b for a, b in zip(plain, _keystream(raw_key, nonce, len(plain)), strict=True))
    mac = hmac.new(raw_key, nonce + cipher, hashlib.sha256).digest()
    return f"{_b64encode(nonce)}.{_b64encode(cipher)}.{_b64encode(mac)}"


def decrypt_string(token: str, *, key: str) -> str | None:
    """Decrypt a value from :func:`encrypt_string`; ``None`` when tampered."""
    try:
        nonce_b64, cipher_b64, mac_b64 = token.split(".", 2)
        nonce = _b64decode(nonce_b64)
        cipher = _b64decode(cipher_b64)
        mac = _b64decode(mac_b64)
    except (ValueError, TypeError):
        return None
    raw_key = hashlib.sha256(key.encode("utf-8")).digest()
    expected = hmac.new(raw_key, nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, mac):
        return None
    plain = bytes(a ^ b for a, b in zip(cipher, _keystream(raw_key, nonce, len(cipher)), strict=True))
    try:
        return plain.decode("utf-8")
    except UnicodeDecodeError:
        return None
