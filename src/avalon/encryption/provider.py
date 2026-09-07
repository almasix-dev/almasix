"""Encryption service provider."""

from __future__ import annotations

from avalon.encryption.encrypter import Encrypter, parse_previous_keys
from avalon.encryption.facade import Crypt
from avalon.providers.provider import ServiceProvider


class EncryptionServiceProvider(ServiceProvider):
    """Binds :class:`Encrypter` from ``app.key`` / ``app.previous_keys``."""

    def register(self) -> None:
        app = self.app

        def factory(_container):
            key = str(app.config.get("app.key", "") or "") or "avalon-insecure-dev-key-change-me"
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
