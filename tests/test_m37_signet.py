"""M37 — Signet-class personal access tokens and SPA cookie auth."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from almasix.auth import AuthenticatableMixin
from almasix.orm import Model, Schema
from almasix.signet import (
    CheckAbilities,
    CheckForAnyAbility,
    HasApiTokens,
    PersonalAccessToken,
    Signet,
    SignetGuard,
    TransientToken,
    is_from_frontend,
)
from almasix.signet.personal_access_token import _hash_token
from almasix.support.helpers import now as clock_now
from tests.orm_support import memory_db  # noqa: F401

pytestmark = pytest.mark.anyio


class TokenUser(HasApiTokens, AuthenticatableMixin, Model):
    table = "token_users"
    fillable = ("email", "name")
    timestamps = False


async def _install_schema() -> None:
    await Schema.create(
        "token_users",
        lambda t: (
            t.id(),
            t.string("email"),
            t.string("name").nullable(),
        ),
    )
    await Schema.create(
        "personal_access_tokens",
        lambda t: (
            t.id(),
            t.morphs("tokenable"),
            t.string("name"),
            t.string("token", 64).unique(),
            t.text("abilities").nullable(),
            t.timestamp("last_used_at").nullable(),
            t.timestamp("expires_at").nullable(),
            t.timestamps(),
        ),
    )


@pytest.fixture
async def tokens_ready(memory_db: Any) -> Any:
    await _install_schema()
    Signet.use_personal_access_token_model(PersonalAccessToken)
    return memory_db


async def test_create_token_hashes_and_returns_plain_text(tokens_ready: Any) -> None:
    user = await TokenUser.create({"email": "ada@almasix.dev", "name": "Ada"})
    issued = await user.create_token("cli", ["server:update"])
    assert "|" in issued.plain_text_token
    token_id, _, plain = issued.plain_text_token.partition("|")
    row = await PersonalAccessToken.query().find(token_id)
    assert row is not None
    assert row.get_raw_attribute("token") == _hash_token(plain)
    assert row.can("server:update")
    assert row.cant("server:delete")
    assert "*" not in (row.get_attribute("abilities") or [])


async def test_find_token_and_token_can(tokens_ready: Any) -> None:
    user = await TokenUser.create({"email": "grace@almasix.dev", "name": "Grace"})
    issued = await user.create_token("phone", ["read", "write"])
    found = await PersonalAccessToken.find_token(issued.plain_text_token)
    assert found is not None
    assert found.can("read")
    assert found.cant("admin")

    user.with_access_token(found)
    assert user.token_can("write")
    assert user.token_cant("admin")


async def test_spa_session_token_can_is_always_true(tokens_ready: Any) -> None:
    user = await TokenUser.create({"email": "spa@almasix.dev", "name": "Spa"})
    # No access token → first-party SPA convenience
    assert user.token_can("anything")
    user.with_access_token(TransientToken(["*"]))
    assert user.token_can("server:update")


async def test_revoke_tokens(tokens_ready: Any) -> None:
    user = await TokenUser.create({"email": "rev@almasix.dev", "name": "Rev"})
    await user.create_token("a")
    await user.create_token("b")
    assert len(await user.tokens().get()) == 2
    await user.tokens_delete()
    assert len(await user.tokens().get()) == 0


async def test_expired_token_is_rejected(tokens_ready: Any) -> None:
    user = await TokenUser.create({"email": "exp@almasix.dev", "name": "Exp"})
    issued = await user.create_token(
        "old",
        ["*"],
        expires_at=clock_now() - timedelta(hours=1),
    )
    found = await PersonalAccessToken.find_token(issued.plain_text_token)
    assert found is not None
    assert found.is_expired()

    guard = SignetGuard("signet")

    class _Req:
        def bearer_token(self) -> str:
            return issued.plain_text_token

    assert await guard.set_user_from_request_token(issued.plain_text_token) is None


async def test_signet_guard_resolves_bearer(tokens_ready: Any) -> None:
    user = await TokenUser.create({"email": "bearer@almasix.dev", "name": "Bearer"})
    issued = await user.create_token("mobile", ["orders:read"])
    guard = SignetGuard("signet")
    resolved = await guard.set_user_from_request_token(issued.plain_text_token)
    assert resolved is not None
    assert resolved.get_attribute("email") == "bearer@almasix.dev"
    assert resolved.token_can("orders:read")
    assert resolved.token_cant("orders:write")


async def test_abilities_middleware(tokens_ready: Any) -> None:
    user = await TokenUser.create({"email": "mid@almasix.dev", "name": "Mid"})
    issued = await user.create_token("scoped", ["check-status"])
    access = await PersonalAccessToken.find_token(issued.plain_text_token)
    assert access is not None
    user.with_access_token(access)

    from almasix.auth.guard import AuthManager, reset_auth, set_auth

    manager = AuthManager()
    manager.guard("signet").once(user)
    token = set_auth(manager)
    try:
        mw = CheckAbilities("check-status")
        called = {"ok": False}

        async def nxt(_request: Any) -> str:
            called["ok"] = True
            return "ok"

        assert await mw.handle(object(), nxt) == "ok"  # type: ignore[arg-type]
        assert called["ok"]

        mw_any = CheckForAnyAbility("missing", "check-status")
        assert await mw_any.handle(object(), nxt) == "ok"  # type: ignore[arg-type]
    finally:
        reset_auth(token)


async def test_is_from_frontend_matches_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    from almasix.config import ConfigRepository, set_repository

    repo = ConfigRepository()
    repo.set("signet", {"stateful": ["spa.example.test", "localhost:3000"]})
    set_repository(repo)

    class Req:
        def __init__(self, headers: dict[str, str]) -> None:
            self.headers = headers

    assert is_from_frontend(Req({"origin": "https://spa.example.test", "host": "api.example.test"}))
    assert is_from_frontend(Req({"referer": "http://localhost:3000/app", "host": "127.0.0.1:8000"}))
    assert not is_from_frontend(Req({"origin": "https://evil.test", "host": "api.example.test"}))


async def test_acting_as_sets_transient_token(tokens_ready: Any) -> None:
    user = await TokenUser.create({"email": "act@almasix.dev", "name": "Act"})
    Signet.acting_as(user, ["profile:read"])
    assert user.token_can("profile:read")
    assert user.token_cant("profile:write")
    taken, guard = Signet.take_acting_as()
    assert taken is user
    assert guard == "signet"


async def test_custom_token_model(tokens_ready: Any) -> None:
    class CustomToken(PersonalAccessToken):
        table = "personal_access_tokens"

    Signet.use_personal_access_token_model(CustomToken)
    assert Signet.personal_access_token_model() is CustomToken
    Signet.use_personal_access_token_model(PersonalAccessToken)
