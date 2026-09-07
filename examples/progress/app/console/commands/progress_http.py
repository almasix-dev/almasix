"""Demo Http.get / fake / assert_sent (M20)."""

from __future__ import annotations

from avalon.client import Http
from avalon.console.command import Command


class ProgressHttpCommand(Command):
    signature = "progress:http"
    description = "Demo Http façade, fakes, and assertions (M20)"

    def handle(self) -> int:
        Http.fake(
            {
                "https://api.example.test/*": Http.response({"ok": True, "pong": True}),
            }
        )
        response = (
            Http.with_token("secret")
            .accept_json()
            .get("https://api.example.test/ping")
        )
        assert response.ok()
        assert response.json("ok") is True
        Http.assert_sent(
            lambda req: req.header("Authorization") == "Bearer secret"
            and req.url.startswith("https://api.example.test/ping")
        )
        self.info(f"ping -> {response.json()}")
        self.success("http client demo ok")
        return 0
