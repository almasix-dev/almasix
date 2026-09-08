"""Application encryption — ``Crypt`` façade and JSON-safe helpers."""

from __future__ import annotations

from almasix.encryption.encrypter import Encrypter, generate_key, parse_previous_keys
from almasix.encryption.exceptions import DecryptException, EncryptException
from almasix.encryption.facade import Crypt
from almasix.encryption.helpers import decrypt, decrypt_string, encrypt, encrypt_string
from almasix.encryption.provider import EncryptionServiceProvider

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
