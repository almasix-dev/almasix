"""The environment file commands — ``env:encrypt`` and ``env:decrypt``.

Avalon's encrypter offers one authenticated cipher and no choice of algorithm,
so these commands have no ``--cipher``: there is nothing to pick between.
"""

from __future__ import annotations

import os
from pathlib import Path

from avalon.console.command import Command
from avalon.encryption.encrypter import Encrypter, generate_key
from avalon.encryption.exceptions import DecryptException

#: Where ``env:decrypt`` looks when no ``--key`` is given.
KEY_VARIABLE = "AVALON_ENV_ENCRYPTION_KEY"


class EnvironmentFileCommand(Command):
    """Shared body: the pair of files, the key, and byte-exact file handling."""

    def root(self) -> Path:
        """The working directory, as ``grail`` was run — not the stale app root."""
        return Path.cwd()

    def file_pair(self) -> tuple[Path, Path] | None:
        """``(.env, .env.encrypted)`` for this run, honouring ``--env=name``."""
        value = self.option("env")
        if value is True:
            self.error(
                "Invalid value for '--env': provide an environment name, e.g. --env=production."
            )
            return None
        name = str(value or "").strip()
        if name and ("/" in name or "\\" in name or name in {".", ".."}):
            self.error(f"Invalid value for '--env': {name!r} is not an environment name.")
            return None
        plain = self.root() / (f".env.{name}" if name else ".env")
        return plain, plain.with_name(plain.name + ".encrypted")

    def given_key(self) -> str | None | bool:
        """The ``--key`` text, ``None`` when absent, ``False`` when unusable."""
        value = self.option("key")
        if value is True:
            self.error(
                "Invalid value for '--key': provide the key itself, e.g. --key=base64:AbC…"
            )
            return False
        text = str(value or "").strip()
        return text or None

    def read_exactly(self, path: Path) -> str:
        """Read without newline translation, so a round trip changes nothing."""
        with path.open("r", encoding="utf-8", newline="") as handle:
            return handle.read()

    def write_exactly(self, path: Path, contents: str) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(contents)

    def refuse_overwrite(self, path: Path) -> bool:
        """``True`` when ``path`` exists and ``--force`` was not given."""
        if not path.exists() or self.option("force"):
            return False
        self.error(f"[{path.name}] already exists. Pass --force to overwrite it.")
        return True


class EnvEncryptCommand(EnvironmentFileCommand):
    signature = (
        "env:encrypt {--key= : Key to encrypt with (default: a freshly generated one)} "
        "{--env= : Encrypt .env.<name> instead of .env} "
        "{--force : Overwrite an existing encrypted file}"
    )
    description = "Encrypt the environment file"

    def handle(self) -> int:
        key = self.given_key()
        if key is False:
            return self.INVALID
        pair = self.file_pair()
        if pair is None:
            return self.INVALID
        plain, encrypted = pair

        if not plain.is_file():
            self.error(f"Environment file [{plain.name}] not found.")
            return self.FAILURE
        if self.refuse_overwrite(encrypted):
            return self.FAILURE

        key = key or generate_key()
        self.write_exactly(encrypted, Encrypter(key).encrypt_string(self.read_exactly(plain)))

        self.success(f"Encrypted [{plain.name}] to [{encrypted.name}].")
        self.line(f"Key: {key}")
        self.comment("Store it now — it is shown once, and the file cannot be read without it.")
        return self.SUCCESS


class EnvDecryptCommand(EnvironmentFileCommand):
    signature = (
        f"env:decrypt {{--key= : Key to decrypt with (default: ${KEY_VARIABLE})}} "
        "{--env= : Decrypt .env.<name>.encrypted instead of .env.encrypted} "
        "{--force : Overwrite an existing environment file}"
    )
    description = "Decrypt an encrypted environment file"

    def handle(self) -> int:
        key = self.given_key()
        if key is False:
            return self.INVALID
        pair = self.file_pair()
        if pair is None:
            return self.INVALID
        plain, encrypted = pair

        key = key or os.environ.get(KEY_VARIABLE, "").strip()
        if not key:
            self.error(f"No key to decrypt with. Pass --key=… or set {KEY_VARIABLE}.")
            return self.FAILURE
        if not encrypted.is_file():
            self.error(f"Encrypted environment file [{encrypted.name}] not found.")
            return self.FAILURE
        if self.refuse_overwrite(plain):
            return self.FAILURE

        try:
            contents = Encrypter(str(key)).decrypt_string(self.read_exactly(encrypted))
        except DecryptException:
            self.error(
                f"Could not decrypt [{encrypted.name}] — the key is wrong, "
                "or the file has been altered since it was written."
            )
            return self.FAILURE

        self.write_exactly(plain, contents)
        self.success(f"Decrypted [{encrypted.name}] to [{plain.name}].")
        return self.SUCCESS
