"""Encryption service provider."""

from __future__ import annotations

from almasix.encryption.encrypter import Encrypter, parse_previous_keys
from almasix.encryption.facade import Crypt
from almasix.providers.provider import ServiceProvider


class EncryptionServiceProvider(ServiceProvider):
    """Binds :class:`Encrypter` from ``app.key`` / ``app.previous_keys``."""

    def register(self) -> None:
        app = self.app

        def factory(_container):
            key = str(app.config.get("app.key", "") or "") or "almasix-insecure-dev-key-change-me"
            previous = parse_previous_keys(app.config.get("app.previous_keys", []))
            encrypter = Encrypter(key, previous)
            Crypt.set_encrypter(encrypter)
            return encrypter

        app.container.singleton(Encrypter, factory)
        app.container.alias(Encrypter, "encrypter")
        app.container.alias(Encrypter, "crypt")

    def boot(self) -> None:
        if self.app.container.bound(Encrypter):
            encrypter = self.app.make(Encrypter)
            Crypt.set_encrypter(encrypter)
