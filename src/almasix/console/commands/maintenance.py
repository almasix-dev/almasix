"""Maintenance mode — ``down`` and ``up``.

Both commands move one marker file under `storage/framework/down`. The
scheduler skips its tasks while it is there; the HTTP middleware answers
503 (or a redirect, or a rendered template) for every request that is not
carrying the bypass cookie.
"""

from __future__ import annotations

import secrets

from almasix.console.command import Command
from almasix.http.maintenance import clear_marker, write_marker


class DownCommand(Command):
    signature = (
        "down "
        "{--redirect= : Redirect requests to this path instead of answering 503} "
        "{--render= : Prism view to render as the 503 body} "
        "{--retry= : Seconds to send in the Retry-After header} "
        "{--refresh= : Seconds to send in the Refresh header} "
        "{--secret= : Bypass secret; visiting ?secret=… sets a cookie} "
        "{--with-secret : Generate a random bypass secret} "
        "{--status=503 : HTTP status to answer with}"
    )
    description = "Put the application into maintenance mode"

    def handle(self) -> int:
        secret = self.option("secret")
        if self.option("with-secret"):
            secret = secrets.token_urlsafe(16)

        retry = self.option("retry")
        refresh = self.option("refresh")
        status = self.option("status") or 503

        path = write_marker(
            self.app.base_path,
            secret=str(secret) if secret else None,
            redirect=str(self.option("redirect") or "") or None,
            retry=int(retry) if retry is not None and str(retry) != "" else None,
            refresh=int(refresh) if refresh is not None and str(refresh) != "" else None,
            status=int(status),
            render=str(self.option("render") or "") or None,
        )
        self.line(f"Application is now in maintenance mode ({path}).")
        if secret:
            self.comment(f"Bypass secret: {secret}")
            self.comment(f"Visit any URL with ?secret={secret} to set the bypass cookie.")
        return self.SUCCESS


class UpCommand(Command):
    signature = "up"
    description = "Bring the application out of maintenance mode"

    def handle(self) -> int:
        clear_marker(self.app.base_path)
        self.line("Application is now live.")
        return self.SUCCESS
