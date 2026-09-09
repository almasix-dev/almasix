"""Demo Signet-class personal access tokens (M37).

Issues a PAT for Ada, hits ``/api/user`` with Bearer auth, checks abilities,
revokes the token, and pokes ``/signet/csrf-cookie``.
"""

from __future__ import annotations

import asyncio
import importlib

from fastapi.testclient import TestClient

from almasix.console.command import Command
from almasix.hashing import Hash
from almasix.signet import PersonalAccessToken
from app.models.user import User


class ProgressTokensCommand(Command):
    signature = "progress:tokens"
    description = "Demo Signet personal access tokens (M37)"

    def handle(self) -> int:
        self.info("Signet-class personal access tokens")
        plain = asyncio.run(self._issue())
        self._http(plain)
        asyncio.run(self._revoke(plain))
        self.info("signet tokens ok")
        self.comment(
            "Client-credentials API keys (not tied to a user) are out of scope — "
            "see the API Tokens docs."
        )
        return self.SUCCESS

    async def _issue(self) -> str:
        user = await User.query().where("email", "=", "ada@almasix.dev").first()
        if user is None:
            user = await User.create(
                {
                    "name": "Ada Lovelace",
                    "email": "ada@almasix.dev",
                    "password": Hash.make("password"),
                }
            )
            self.line("  seeded ada@almasix.dev / password")

        issued = await user.create_token("progress-cli", ["server:update", "orders:read"])
        self.line(f"  create_token -> {issued.plain_text_token[:18]}…")
        assert "|" in issued.plain_text_token

        found = await PersonalAccessToken.find_token(issued.plain_text_token)
        assert found is not None
        assert found.can("server:update")
        assert found.cant("server:delete")
        self.line("  abilities -> server:update yes, server:delete no")
        return issued.plain_text_token

    def _client(self) -> TestClient:
        # Full HTTP bootstrap (middleware aliases + routes) — console boot skips both.
        module = importlib.import_module("bootstrap.app")
        return TestClient(module.asgi)

    def _http(self, plain: str) -> None:
        client = self._client()
        denied = client.get("/api/user")
        assert denied.status_code in (401, 403), denied.status_code
        self.line(f"  GET /api/user (no token) -> {denied.status_code}")

        ok = client.get("/api/user", headers={"Authorization": f"Bearer {plain}"})
        assert ok.status_code == 200, ok.text
        body = ok.json()
        assert body["user"]["email"] == "ada@almasix.dev"
        assert body["abilities"]["server:update"] is True
        self.line("  GET /api/user (Bearer PAT) -> 200 + abilities")

        csrf = client.get("/signet/csrf-cookie")
        assert csrf.status_code == 204, csrf.status_code
        self.line("  GET /signet/csrf-cookie -> 204")

    async def _revoke(self, plain: str) -> None:
        found = await PersonalAccessToken.find_token(plain)
        assert found is not None
        await found.delete()
        after = self._client().get("/api/user", headers={"Authorization": f"Bearer {plain}"})
        assert after.status_code in (401, 403), after.status_code
        self.line(f"  after revoke -> {after.status_code}")
