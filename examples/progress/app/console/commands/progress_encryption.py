"""Demo Crypt façade — encrypt / decrypt with APP_KEY."""

from __future__ import annotations

from avalon.console.command import Command
from avalon.encryption import Crypt, DecryptException


class ProgressEncryptionCommand(Command):
    signature = "progress:encryption"
    description = "Demo Crypt.encrypt / decrypt (M17)"

    def handle(self) -> int:
        payload = {"token": "secret-api-token", "n": 42}
        encrypted = Crypt.encrypt(payload)
        self.info(f"Crypt.encrypt → {encrypted[:48]}…")
        restored = Crypt.decrypt(encrypted)
        self.info(f"Crypt.decrypt → {restored!r}")

        raw = Crypt.encrypt_string("plain-text-secret")
        self.info(f"Crypt.encrypt_string → {raw[:48]}…")
        self.info(f"Crypt.decrypt_string → {Crypt.decrypt_string(raw)!r}")

        try:
            Crypt.decrypt_string(encrypted[:-4] + "xxxx")
        except DecryptException:
            self.comment("tamper detected (DecryptException) — ok")

        self.success("encryption demo ok")
        return 0
