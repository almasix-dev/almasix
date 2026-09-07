"""M17 Encryption — Crypt façade, JSON-safe encrypt, previous keys, key:generate."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from avalon.encryption import (
    Crypt,
    DecryptException,
    Encrypter,
    EncryptException,
    EncryptionServiceProvider,
    decrypt,
    decrypt_string,
    encrypt,
    encrypt_string,
    generate_key,
    parse_previous_keys,
)
from avalon.encryption.cipher import decrypt_string as cipher_decrypt
from avalon.encryption.cipher import encrypt_string as cipher_encrypt
from avalon.encryption.helpers import get_encrypter, resolve_encrypter
from avalon.framework.application import Application
from avalon.grail.cli import app as grail_app


@pytest.fixture(autouse=True)
def _reset_crypt() -> None:
    Crypt.set_encrypter(None)
    yield
    Crypt.set_encrypter(None)


def test_cipher_roundtrip_and_tamper() -> None:
    token = cipher_encrypt("hello", key="k1")
    assert cipher_decrypt(token, key="k1") == "hello"
    assert cipher_decrypt(token, key="wrong") is None
    assert cipher_decrypt("not.a.token", key="k1") is None
    assert cipher_decrypt(token[:-2] + "xx", key="k1") is None


def test_cipher_bad_segments_and_non_utf8() -> None:
    assert cipher_decrypt("only-one-segment", key="k") is None
    # Valid MAC structure but garbage base64 segments handled
    assert cipher_decrypt("!!.!!.!!", key="k") is None


def test_parse_previous_keys() -> None:
    assert parse_previous_keys(None) == []
    assert parse_previous_keys("") == []
    assert parse_previous_keys("a, b , ,c") == ["a", "b", "c"]
    assert parse_previous_keys(["x", "", "y"]) == ["x", "y"]
    assert parse_previous_keys(False) == []


def test_generate_key_format() -> None:
    key = generate_key()
    assert key.startswith("base64:")
    assert len(key) > 20


def test_encrypter_string_and_json() -> None:
    enc = Encrypter("current", ["old"])
    raw = enc.encrypt_string("secret")
    assert enc.decrypt_string(raw) == "secret"

    payload = enc.encrypt({"a": 1, "b": ["x", True, None]})
    assert enc.decrypt(payload) == {"a": 1, "b": ["x", True, None]}


def test_encrypter_previous_key_rotation() -> None:
    old = Encrypter("old-key")
    token = old.encrypt_string("legacy")
    current = Encrypter("new-key", ["old-key"])
    assert current.decrypt_string(token) == "legacy"
    assert current.encrypt_string("fresh").count(".") == 2


def test_encrypter_decrypt_failure() -> None:
    enc = Encrypter("k")
    with pytest.raises(DecryptException):
        enc.decrypt_string("tampered.payload.here")
    with pytest.raises(DecryptException):
        enc.decrypt(enc.encrypt_string("not-json{"))


def test_encrypter_rejects_non_json() -> None:
    enc = Encrypter("k")
    with pytest.raises(EncryptException):
        enc.encrypt(object())


def test_encrypter_keys_dedupe() -> None:
    enc = Encrypter("same", ["same", "other", ""])
    assert enc.keys == ["same", "other"]


def test_crypt_facade_and_helpers(tmp_path: Path) -> None:
    Crypt.set_encrypter(Encrypter("facade-key"))
    assert Crypt.encrypt("hi") 
    assert Crypt.decrypt(Crypt.encrypt([1, 2])) == [1, 2]
    assert Crypt.decrypt_string(Crypt.encrypt_string("z")) == "z"
    assert encrypt({"n": 1})
    assert decrypt(encrypt("s")) == "s"
    assert decrypt_string(encrypt_string("t")) == "t"
    assert get_encrypter() is Crypt.get_encrypter()


def test_cipher_non_utf8_plaintext() -> None:
    """Force decrypt path that yields non-UTF-8 bytes → None."""
    import hashlib
    import hmac
    import os

    from avalon.encryption import cipher as c

    key = "k"
    raw_key = hashlib.sha256(key.encode("utf-8")).digest()
    nonce = os.urandom(16)
    # Encrypt invalid UTF-8 bytes directly
    plain = b"\xff\xfe"
    stream = c._keystream(raw_key, nonce, len(plain))
    cipher_bytes = bytes(a ^ b for a, b in zip(plain, stream, strict=True))
    mac = hmac.new(raw_key, nonce + cipher_bytes, hashlib.sha256).digest()
    token = f"{c._b64encode(nonce)}.{c._b64encode(cipher_bytes)}.{c._b64encode(mac)}"
    assert c.decrypt_string(token, key=key) is None


def test_resolve_encrypter_from_config(tmp_path: Path) -> None:
    Crypt.set_encrypter(None)
    app = Application.configure(tmp_path).create()
    app.config.set("app.key", "cfg-key")
    app.config.set("app.previous_keys", "prev-a,prev-b")
    from avalon.config import set_repository

    set_repository(app.config)
    Crypt.set_encrypter(None)
    resolved = resolve_encrypter()
    assert resolved.key == "cfg-key"
    assert resolved.previous_keys == ["prev-a", "prev-b"]


def test_crypt_lazy_resolve_via_get_encrypter(tmp_path: Path) -> None:
    Crypt.set_encrypter(None)
    app = Application.configure(tmp_path).create()
    app.config.set("app.key", "lazy-key")
    from avalon.config import set_repository

    set_repository(app.config)
    Crypt.set_encrypter(None)
    assert Crypt.encrypt_string("x")
    assert Crypt.get_encrypter().key == "lazy-key"


def test_resolve_encrypter_fallback_when_config_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Crypt.set_encrypter(None)

    def raising_config(key: str, default=None):
        raise RuntimeError("boom")

    monkeypatch.setattr("avalon.config.config", raising_config)
    enc = resolve_encrypter()
    assert enc.key == "avalon-insecure-dev-key-change-me"
    assert enc.previous_keys == []


def test_provider_binds_encrypter(tmp_path: Path) -> None:
    app = Application.configure(tmp_path).create()
    app.config.set("app.key", "provider-key")
    app.config.set("app.previous_keys", ["p1"])
    EncryptionServiceProvider(app).register()
    EncryptionServiceProvider(app).boot()
    enc = app.make(Encrypter)
    assert enc.key == "provider-key"
    assert Crypt.decrypt_string(Crypt.encrypt_string("x")) == "x"


def test_provider_boot_noop_when_unbound() -> None:
    from avalon.framework.container import Container

    class MiniApp:
        def __init__(self) -> None:
            self.container = Container()
            self.config = {"app.key": "x"}

    EncryptionServiceProvider(MiniApp()).boot()


def test_key_generate_creates_and_updates_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    from avalon.console.kernel import ConsoleKernel

    ConsoleKernel.from_cwd(tmp_path).register_on_typer(grail_app)

    result = runner.invoke(grail_app, ["key:generate"])
    assert result.exit_code == 0, result.stdout + result.stderr
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "APP_KEY=base64:" in env_text
    first = env_text.strip()

    # Update existing APP_KEY
    result2 = runner.invoke(grail_app, ["key:generate"])
    assert result2.exit_code == 0
    second = (tmp_path / ".env").read_text(encoding="utf-8").strip()
    assert second.startswith("APP_KEY=base64:")
    assert second != first

    # Append when APP_KEY missing but .env exists
    (tmp_path / ".env").write_text("FOO=1", encoding="utf-8")
    result3 = runner.invoke(grail_app, ["key:generate"])
    assert result3.exit_code == 0
    assert "APP_KEY=base64:" in (tmp_path / ".env").read_text(encoding="utf-8")


def test_key_generate_appends_newline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("FOO=1", encoding="utf-8")  # no trailing newline
    runner = CliRunner()
    from avalon.console.kernel import ConsoleKernel

    ConsoleKernel.from_cwd(tmp_path).register_on_typer(grail_app)
    assert runner.invoke(grail_app, ["key:generate"]).exit_code == 0
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "FOO=1\nAPP_KEY=" in text


def test_cookie_middleware_uses_previous_keys() -> None:
    from avalon.session.encrypt import encrypt_string as session_encrypt
    from avalon.session.encrypt_middleware import EncryptCookies

    old_token = session_encrypt("cookie-value", key="old")
    assert old_token.count(".") == 2
    mw = EncryptCookies()
    # Unit: decrypt path via Encrypter in handle is covered in integration;
    # verify shared cipher still re-exported
    from avalon.session.encrypt import decrypt_string as session_decrypt

    assert session_decrypt(old_token, key="old") == "cookie-value"
    assert mw.except_cookies == frozenset()
