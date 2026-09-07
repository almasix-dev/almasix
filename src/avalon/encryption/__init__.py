"""Application encryption — ``Crypt`` façade and JSON-safe helpers."""

from __future__ import annotations

from avalon.encryption.encrypter import Encrypter, generate_key, parse_previous_keys
from avalon.encryption.exceptions import DecryptException, EncryptException
from avalon.encryption.facade import Crypt
from avalon.encryption.helpers import decrypt, decrypt_string, encrypt, encrypt_string
from avalon.encryption.provider import EncryptionServiceProvider

__all__ = [
    "Crypt",
    "DecryptException",
    "EncryptException",
    "Encrypter",
    "EncryptionServiceProvider",
    "decrypt",
    "decrypt_string",
    "encrypt",
    "encrypt_string",
    "generate_key",
    "parse_previous_keys",
]
