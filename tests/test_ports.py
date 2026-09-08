"""Tests for Laravel-style port discovery."""

from __future__ import annotations

import socket
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from avalon.grail.cli import app as grail_app
from avalon.grail.ports import (
    DEFAULT_PORT,
    MAX_PORT,
    NoFreePortError,
    find_available_port,
    is_port_free,
)
from avalon.installer.scaffold import scaffold_app

runner = CliRunner()


def test_default_port_constants() -> None:
    assert DEFAULT_PORT == 3000
    assert MAX_PORT == 3099


def test_find_available_port_skips_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    busy = {3000, 3001}

    def fake_free(host: str, port: int) -> bool:
        return port not in busy

    monkeypatch.setattr("avalon.grail.ports.is_port_free", fake_free)
    assert find_available_port(start=3000, end=3099) == 3002


def test_find_available_port_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("avalon.grail.ports.is_port_free", lambda host, port: False)
    with pytest.raises(NoFreePortError, match="No free port"):
        find_available_port(start=3000, end=3002)


def test_is_port_free_roundtrip() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        assert is_port_free("127.0.0.1", port) is False
    assert is_port_free("127.0.0.1", port) is True


def test_serve_auto_selects_next_port(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = scaffold_app("port_app", destination=tmp_path / "port_app")
    monkeypatch.chdir(root)

    def fake_find(host: str, start: int, end: int) -> int:
        assert start == DEFAULT_PORT
        assert end == MAX_PORT
        return 3003

    monkeypatch.setattr("avalon.console.commands.runtime.find_available_port", fake_find)
    mock_run = MagicMock()
    monkeypatch.setattr("avalon.console.commands.runtime.uvicorn.run", mock_run)

    result = runner.invoke(grail_app, ["serve"])
    assert result.exit_code == 0, result.stdout
    assert "http://127.0.0.1:3003" in result.stdout
    assert "3000 is in use" in result.stdout
    assert mock_run.call_args.kwargs["port"] == 3003


def test_serve_uses_requested_port_when_free(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = scaffold_app("port_app2", destination=tmp_path / "port_app2")
    monkeypatch.chdir(root)
    monkeypatch.setattr(
        "avalon.console.commands.runtime.find_available_port",
        lambda host, start, end: start,
    )
    mock_run = MagicMock()
    monkeypatch.setattr("avalon.console.commands.runtime.uvicorn.run", mock_run)

    result = runner.invoke(grail_app, ["serve", "--port", "3010"])
    assert result.exit_code == 0, result.stdout
    assert "3010 is in use" not in result.stdout
    assert mock_run.call_args.kwargs["port"] == 3010
