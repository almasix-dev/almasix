"""Local sendmail binary transport."""

from __future__ import annotations

import shlex
import subprocess

from almasix.mail.message import SentMessage
from almasix.mail.transports.smtp import SmtpTransport


class SendmailTransport:
    """Pipe a rendered message to ``sendmail`` (Laravel ``sendmail`` driver)."""

    def __init__(self, *, path: str = "/usr/sbin/sendmail -bs") -> None:
        self.path = path

    def send(self, message: SentMessage) -> None:
        email = SmtpTransport._build_email(message)
        raw = email.as_bytes()
        cmd = shlex.split(self.path)
        # ``-bs`` speaks SMTP on stdin; ``-t`` reads recipients from headers.
        if "-bs" in cmd:
            # For tests without a real sendmail, allow injecting via env path that fails softly
            # when binary missing — raise clear error.
            try:
                proc = subprocess.run(
                    cmd,
                    input=raw,
                    capture_output=True,
                    check=False,
                )
            except FileNotFoundError as exc:
                raise RuntimeError(f"Sendmail binary not found: {cmd[0]!r}") from exc
            if proc.returncode != 0:
                raise RuntimeError(
                    f"Sendmail failed ({proc.returncode}): {proc.stderr.decode(errors='replace')}"
                )
            return
        # Default: ``sendmail -t -i``
        if "-t" not in cmd:
            cmd = [*cmd, "-t", "-i"]
        try:
            proc = subprocess.run(cmd, input=raw, capture_output=True, check=False)
        except FileNotFoundError as exc:
            raise RuntimeError(f"Sendmail binary not found: {cmd[0]!r}") from exc
        if proc.returncode != 0:
            raise RuntimeError(
                f"Sendmail failed ({proc.returncode}): {proc.stderr.decode(errors='replace')}"
            )
