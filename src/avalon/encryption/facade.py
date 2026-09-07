"""Static ``Crypt`` façade over :class:`~avalon.encryption.encrypter.Encrypter`."""

from __future__ import annotations

from typing import Any

from avalon.encryption.encrypter import Encrypter


class Crypt:
    """App-facing encryption helpers."""

    _encrypter: Encrypter | None = None

    @classmethod
    def set_encrypter(cls, encrypter: Encrypter | None) -> None:
        cls._encrypter = encrypter

    @classmethod
    def get_encrypter(cls) -> Encrypter:
        if cls._encrypter is None:
            from avalon.encryption.helpers import resolve_encrypter

            cls._encrypter = resolve_encrypter()
        return cls._encrypter

    @classmethod
    def encrypt(cls, value: Any) -> str:
        return cls.get_encrypter().encrypt(value)

    @classmethod
    def decrypt(cls, payload: str) -> Any:
        return cls.get_encrypter().decrypt(payload)

    @classmethod
    def encrypt_string(cls, value: str) -> str:
        return cls.get_encrypter().encrypt_string(value)

    @classmethod
    def decrypt_string(cls, payload: str) -> str:
        return cls.get_encrypter().decrypt_string(payload)
