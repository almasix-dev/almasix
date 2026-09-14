"""Unit tests for ``smith ide:index`` / ``almasix.ide.index``."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from almasix.ide.index import build_ide_index, dump_index_json

PROGRESS = Path(__file__).resolve().parents[1] / "examples" / "progress"


def test_build_ide_index_progress() -> None:
    payload = build_ide_index(PROGRESS)
    assert payload["ok"] is True
    assert payload["error"] is None
    assert len(payload["views"]) >= 1
    assert len(payload["config_keys"]) >= 1
    assert len(payload["validation_rules"]) >= 50
    assert "required" in payload["validation_rules"]
    assert len(payload["smith_commands"]) >= 20
    assert "ide:index" in payload["smith_commands"]
    assert "serve" in payload["smith_commands"]
    assert isinstance(payload["gates"], list)
    assert isinstance(payload["components"], dict)
    assert isinstance(payload["casts"], list)
    assert "int" in payload["casts"]
    assert isinstance(payload["directives"], list)
    assert "if" in payload["directives"]
    # JSON round-trip
    data = json.loads(dump_index_json(PROGRESS))
    assert data["ok"] is True
    assert data["base_path"] == str(PROGRESS.resolve())


def test_ide_index_cli_json() -> None:
    result = subprocess.run(
        [sys.executable, "smith", "ide:index", "--json", "--path", str(PROGRESS)],
        cwd=PROGRESS,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert "routes" in payload
    assert "validation_rules" in payload


def test_ide_index_human() -> None:
    result = subprocess.run(
        [sys.executable, "smith", "ide:index", "--path", str(PROGRESS)],
        cwd=PROGRESS,
        capture_output=True,
        text=True,
        check=False,
    )
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    assert "ide:index ok" in out
    assert "views" in out
