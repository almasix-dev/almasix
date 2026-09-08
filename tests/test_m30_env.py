"""M30 — ``env:encrypt`` and ``env:decrypt``.

The round trip has to be byte-exact: an environment file is full of comments,
blank lines and spacing that people put there on purpose.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from almasix.console.commands.env import KEY_VARIABLE
from almasix.console.kernel import ConsoleKernel

PLAIN = """# Application
APP_NAME="Almasix DEMO"
APP_ENV=local

# Database — the blank line above and this comment must survive
DB_CONNECTION=sqlite
DB_PASSWORD="a b  c"
"""


@pytest.fixture
def kernel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ConsoleKernel:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(KEY_VARIABLE, raising=False)
    built = ConsoleKernel.for_cwd(tmp_path)
    built.discover_framework_commands()
    return built


def printed_key(capsys: pytest.CaptureFixture[str]) -> tuple[str, str]:
    """The key ``env:encrypt`` printed, with the output it came in."""
    out = capsys.readouterr().out
    line = next(line for line in out.splitlines() if line.startswith("Key: "))
    return line[len("Key: ") :].strip(), out


def test_the_round_trip_changes_nothing_at_all(
    tmp_path: Path, kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / ".env"
    source.write_text(PLAIN, encoding="utf-8")

    assert kernel.run_argv("env:encrypt", []) == 0
    key, out = printed_key(capsys)

    assert "Encrypted [.env] to [.env.encrypted]." in out
    assert out.count(key) == 1  # shown once, never again
    assert PLAIN not in (tmp_path / ".env.encrypted").read_text(encoding="utf-8")

    source.unlink()
    assert kernel.run_argv("env:decrypt", ["--key", key]) == 0

    decrypted = capsys.readouterr().out
    assert "Decrypted [.env.encrypted] to [.env]." in decrypted
    assert key not in decrypted  # a decrypt never repeats the key
    assert source.read_text(encoding="utf-8") == PLAIN


def test_line_endings_survive_the_round_trip(
    tmp_path: Path, kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    """Windows line endings, and no newline at the end, come back untouched."""
    raw = b"# comment\r\nAPP_ENV=local\r\n\r\nAPP_DEBUG=true"
    source = tmp_path / ".env"
    source.write_bytes(raw)

    assert kernel.run_argv("env:encrypt", []) == 0
    key, _ = printed_key(capsys)

    assert kernel.run_argv("env:decrypt", ["--key", key, "--force"]) == 0
    assert source.read_bytes() == raw


def test_a_named_environment_gets_its_own_pair_of_files(
    tmp_path: Path, kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".env.production").write_text(PLAIN, encoding="utf-8")

    assert kernel.run_argv("env:encrypt", ["--env", "production"]) == 0
    key, out = printed_key(capsys)

    assert "Encrypted [.env.production] to [.env.production.encrypted]." in out
    assert (tmp_path / ".env.production.encrypted").is_file()
    assert not (tmp_path / ".env.encrypted").exists()

    (tmp_path / ".env.production").unlink()
    assert kernel.run_argv("env:decrypt", ["--env", "production", "--key", key]) == 0
    assert (tmp_path / ".env.production").read_text(encoding="utf-8") == PLAIN


def test_a_key_can_be_supplied_instead_of_generated(
    tmp_path: Path, kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".env").write_text(PLAIN, encoding="utf-8")

    assert kernel.run_argv("env:encrypt", ["--key", "base64:hunter2"]) == 0
    key, _ = printed_key(capsys)

    assert key == "base64:hunter2"


def test_the_key_can_come_from_the_environment_on_decrypt(
    tmp_path: Path, kernel: ConsoleKernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text(PLAIN, encoding="utf-8")
    assert kernel.run_argv("env:encrypt", ["--key", "base64:hunter2"]) == 0
    (tmp_path / ".env").unlink()
    monkeypatch.setenv(KEY_VARIABLE, "base64:hunter2")

    assert kernel.run_argv("env:decrypt", []) == 0
    assert (tmp_path / ".env").read_text(encoding="utf-8") == PLAIN


def test_the_wrong_key_fails_without_touching_the_file(
    tmp_path: Path, kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".env").write_text(PLAIN, encoding="utf-8")
    assert kernel.run_argv("env:encrypt", ["--key", "base64:right"]) == 0
    (tmp_path / ".env").write_text("KEEP=me\n", encoding="utf-8")
    capsys.readouterr()

    assert kernel.run_argv("env:decrypt", ["--key", "base64:wrong", "--force"]) == 1

    assert "the key is wrong, or the file has been altered" in capsys.readouterr().err
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "KEEP=me\n"


def test_decrypt_needs_a_key_from_somewhere(
    tmp_path: Path, kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".env.encrypted").write_text("anything", encoding="utf-8")

    assert kernel.run_argv("env:decrypt", []) == 1
    assert f"Pass --key=… or set {KEY_VARIABLE}." in capsys.readouterr().err


def test_encrypt_reports_a_missing_environment_file(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("env:encrypt", []) == 1
    assert "Environment file [.env] not found." in capsys.readouterr().err


def test_decrypt_reports_a_missing_encrypted_file(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("env:decrypt", ["--key", "base64:whatever"]) == 1
    assert "Encrypted environment file [.env.encrypted] not found." in capsys.readouterr().err


def test_neither_command_overwrites_without_force(
    tmp_path: Path, kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".env").write_text(PLAIN, encoding="utf-8")
    assert kernel.run_argv("env:encrypt", ["--key", "base64:k"]) == 0
    capsys.readouterr()

    assert kernel.run_argv("env:encrypt", ["--key", "base64:k"]) == 1
    assert "[.env.encrypted] already exists. Pass --force to overwrite it." in capsys.readouterr().err

    assert kernel.run_argv("env:decrypt", ["--key", "base64:k"]) == 1
    assert "[.env] already exists. Pass --force to overwrite it." in capsys.readouterr().err

    assert kernel.run_argv("env:encrypt", ["--key", "base64:k", "--force"]) == 0
    assert kernel.run_argv("env:decrypt", ["--key", "base64:k", "--force"]) == 0


@pytest.mark.parametrize("command", ["env:encrypt", "env:decrypt"])
def test_a_key_flag_with_nothing_after_it_is_rejected(
    command: str, kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv(command, ["--key"]) == 2
    assert "Invalid value for '--key'" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["env:encrypt", "env:decrypt"])
def test_an_env_flag_with_nothing_after_it_is_rejected(
    command: str, kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv(command, ["--key", "base64:k", "--env"]) == 2
    assert "Invalid value for '--env'" in capsys.readouterr().err


@pytest.mark.parametrize("name", ["../secrets", "a/b", "..", "back\\slash"])
def test_an_environment_name_that_is_a_path_is_rejected(
    name: str, kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("env:encrypt", ["--env", name]) == 2
    assert "is not an environment name" in capsys.readouterr().err
