"""M7 unit tests — hashing, guards, attempt, passwords."""

from __future__ import annotations

import pytest

from avalon.auth.guard import AuthManager, Guard, SessionGuard, auth
from avalon.auth.passwords import Password, get_password_manager
from avalon.auth.providers import MemoryUserProvider
from avalon.hashing import Hash, HashManager, set_hash_manager
from avalon.session.signing import sign_payload, unsign_payload
from avalon.session.encrypt import decrypt_string, encrypt_string
from avalon.session.store import Session, set_session, reset_session


@pytest.fixture(autouse=True)
def _hash_manager() -> None:
    manager = HashManager()
    manager.configure(rounds=4)  # fast tests
    set_hash_manager(manager)
    yield
    set_hash_manager(None)


def test_signed_cookie_roundtrip() -> None:
    token = sign_payload({"a": 1}, key="secret", max_age=3600)
    assert unsign_payload(token, key="secret", max_age=3600) == {"a": 1}
    assert unsign_payload(token, key="wrong", max_age=3600) is None


def test_encrypt_cookie_roundtrip() -> None:
    cipher = encrypt_string("hello.world.payload", key="app-key")
    assert decrypt_string(cipher, key="app-key") == "hello.world.payload"


def test_hash_make_check_rehash() -> None:
    hashed = Hash.make("secret")
    assert Hash.check("secret", hashed)
    assert not Hash.check("nope", hashed)
    assert Hash.is_hashed(hashed)
    assert not Hash.needs_rehash(hashed)
    set_hash_manager(HashManager())
    get = __import__("avalon.hashing", fromlist=["get_hash_manager"]).get_hash_manager()
    get.configure(rounds=5)
    assert Hash.needs_rehash(hashed)


def test_session_flash_ages() -> None:
    session = Session()
    session.flash("status", "ok")
    session.age_flash()
    assert session.get("status") == "ok"
    session.age_flash()
    assert session.get("status") is None


@pytest.mark.asyncio
async def test_session_guard_attempt_login_logout() -> None:
    provider = MemoryUserProvider(
        [{"id": 1, "email": "ada@example.com", "name": "Ada", "password": Hash.make("password")}]
    )
    guard = SessionGuard("web", provider)
    session = Session()
    token = set_session(session)
    try:
        assert not await guard.attempt({"email": "ada@example.com", "password": "wrong"})
        assert await guard.attempt({"email": "ada@example.com", "password": "password"})
        assert guard.check()
        assert guard.id() == 1
        await guard.logout()
        assert guard.guest()
    finally:
        reset_session(token)


@pytest.mark.asyncio
async def test_password_broker_flow() -> None:
    provider = MemoryUserProvider(
        [{"id": 1, "email": "ada@example.com", "password": Hash.make("old")}]
    )
    manager = AuthManager()
    manager._providers["users"] = provider  # noqa: SLF001
    token_box: dict[str, str] = {}

    async def deliver(user, token: str) -> None:
        token_box["token"] = token

    get_password_manager().create_url_using(deliver)
    # Force broker to use our provider
    broker = get_password_manager().broker("users")
    broker.provider = provider
    broker.send_callback = deliver

    status = await Password.send_reset_link({"email": "missing@example.com"})
    assert status == Password.INVALID_USER

    status = await Password.send_reset_link({"email": "ada@example.com"})
    assert status == Password.RESET_LINK_SENT
    assert "token" in token_box

    async def apply(user, password: str) -> None:
        user["password"] = Hash.make(password)

    status = await broker.reset(
        {
            "email": "ada@example.com",
            "token": token_box["token"],
            "password": "new-password",
        },
        apply,
    )
    assert status == Password.PASSWORD_RESET
    user = await provider.retrieve_by_credentials({"email": "ada@example.com"})
    assert Hash.check("new-password", user["password"])


def test_auth_helper_outside_request() -> None:
    assert auth().guest()
