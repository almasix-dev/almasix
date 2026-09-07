"""``key:generate`` — write a new ``APP_KEY`` into ``.env``."""

from __future__ import annotations

import re
from pathlib import Path

from avalon.console.command import Command
from avalon.encryption.encrypter import generate_key


class KeyGenerateCommand(Command):
    signature = "key:generate"
    description = "Set the application key (APP_KEY) in .env"

    def handle(self) -> int:
        key = generate_key()
        env_path = Path.cwd() / ".env"
        if not env_path.is_file():
            env_path.write_text(f"APP_KEY={key}\n", encoding="utf-8")
            self.info(f"Created .env with APP_KEY={key}")
            return 0

        text = env_path.read_text(encoding="utf-8")
        pattern = re.compile(r"^APP_KEY=.*$", re.MULTILINE)
        if pattern.search(text):
            text = pattern.sub(f"APP_KEY={key}", text, count=1)
        else:
            if text and not text.endswith("\n"):
                text += "\n"
            text += f"APP_KEY={key}\n"
        env_path.write_text(text, encoding="utf-8")
        self.info(f"Application key set successfully: {key}")
        return 0
