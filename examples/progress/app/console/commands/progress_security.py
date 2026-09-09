"""Demo security headers, CORS, and maintenance mode (M34)."""

from __future__ import annotations

import json

from almasix.console.command import Command
from almasix.http.cors import cors_settings
from almasix.http.maintenance import clear_marker, write_marker
from almasix.http.security import DEFAULT_HEADERS
from almasix.routing import Route, Router, set_router


class ProgressSecurityCommand(Command):
    signature = "progress:security"
    description = "Demo security headers, CORS, and maintenance mode (M34)"

    def handle(self) -> int:
        self._headers()
        self._cors()
        self._maintenance()
        self.success("security demo ok")
        return 0

    def _headers(self) -> None:
        self.info("security headers (on the web stack by default)")
        for name, value in DEFAULT_HEADERS.items():
            self.line(f"    {name:28} {value}")
        self.line("    Content-Security-Policy     opt-in via SecurityHeaders(csp=...)")
        self.line("    Strict-Transport-Security   opt-in via SecurityHeaders(hsts=True)")
        self.line("    csp_nonce()                 available in Prism templates")

    def _cors(self) -> None:
        settings = cors_settings(self.app.config.get("cors") or {})
        self.info("CORS")
        self.line(f"    paths              -> {settings['paths']}")
        self.line(f"    allowed_origins    -> {settings['allowed_origins']}")
        self.line(f"    allowed_methods    -> {settings['allowed_methods']}")
        self.line(f"    supports_credentials -> {settings['supports_credentials']}")
        self.line("    a path outside `paths` gets no Access-Control headers")

    def _maintenance(self) -> None:
        previous = set_router(Router())
        try:
            Route.get("/", lambda: {"ok": True}).name("home")
            path = write_marker(
                self.app.base_path,
                secret="demo-secret",
                retry=60,
                status=503,
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.info("maintenance mode")
            self.line(f"    marker             -> {path}")
            self.line(f"    payload            -> {payload}")
            self.line("    HTTP               -> 503 with Retry-After: 60")
            self.line("    ?secret=demo-secret -> sets the bypass cookie, then 200")
            self.line("    smith up           -> removes the marker")
        finally:
            clear_marker(self.app.base_path)
            set_router(previous)
        self.line("    marker after up     -> gone")
