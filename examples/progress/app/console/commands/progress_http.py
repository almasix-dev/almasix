"""Demo Http.get / fake / assert_sent (M20)."""

from __future__ import annotations

from almasix.client import Http
from almasix.console.command import Command


class ProgressHttpCommand(Command):
    signature = "progress:http"
    description = "Demo Http façade, fakes, and assertions (M20)"

    def handle(self) -> int:
        Http.prevent_stray_requests()
        Http.fake(
            {
                "https://api.example.test/flaky": Http.sequence()
                .push_status(503)
                .push({"ok": True, "recovered": True}),
                "https://api.example.test/*": Http.response({"ok": True, "pong": True}),
            }
        )

        response = (
            Http.with_token("secret").accept_json().get("https://api.example.test/ping")
        )
        assert response.ok()
        assert response.json("ok") is True
        Http.assert_sent(
            lambda req, resp: req.has_header("Authorization", "Bearer secret") and resp.ok()
        )
        self.info(f"ping -> {response.json()}")

        retried = Http.retry(3, [10, 20]).get("https://api.example.test/flaky")
        assert retried.json("recovered") is True
        self.info(f"flaky -> recovered after {len(Http.recorded()) - 1} attempts")

        responses = Http.pool(
            lambda pool: [
                pool.as_("ping").get("https://api.example.test/ping"),
                pool.with_header("X-Demo", "1").get("https://api.example.test/pong"),
            ],
            concurrency=2,
        )
        assert responses["ping"].ok() and responses[0].ok()
        self.info(f"pool -> {len(responses)} concurrent responses")

        batch = (
            Http.batch(
                lambda batch: [
                    batch.as_("first").get("https://api.example.test/one"),
                    batch.as_("second").get("https://api.example.test/two"),
                ]
            )
            .progress(lambda batch, key, resp: self.line(f"  batch {key} -> {resp.status()}"))
            .then(lambda batch, results: self.line(f"  batch done: {len(results)}"))
        )
        batch.send()
        assert batch.finished() and not batch.has_failures()

        Http.assert_sequences_are_empty()
        self.success("http client demo ok")
        return 0
