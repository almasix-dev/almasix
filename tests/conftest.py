"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.support import purge_generated_app_modules


@pytest.fixture(autouse=True)
def _forget_generated_app_modules() -> Iterator[None]:
    """Never let one test's ``app`` package answer another test's import.

    Tests scaffold applications into temporary directories, and Python caches
    the first ``app`` package it imports. Without this, a test that generates
    half an app decides what ``app.providers`` means for every test after it —
    which passes or fails depending on collection order.
    """
    yield
    purge_generated_app_modules()


@pytest.fixture
def clean_app_modules() -> Iterator[None]:
    purge_generated_app_modules()
    yield
    purge_generated_app_modules()


@pytest.fixture
def app_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_app_modules: None) -> Path:
    """Scaffold a disposable app and chdir into it with import path set."""
    from avalon.installer.scaffold import scaffold_app

    root = scaffold_app("regress_app", destination=tmp_path / "regress_app")
    monkeypatch.chdir(root)
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.delenv("APP_NAME", raising=False)
    return root
