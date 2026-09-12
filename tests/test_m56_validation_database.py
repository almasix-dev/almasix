"""M56 — exists / unique against SQLite."""

from __future__ import annotations

import pytest

from almasix.orm.facade import DB
from almasix.validation import validator
from tests.orm_support import memory_db  # noqa: F401


@pytest.mark.asyncio
async def test_exists_and_unique(memory_db) -> None:
    del memory_db
    await DB.statement("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE)")
    await DB.table("users").insert({"email": "ada@example.com"})

    assert validator(
        {"email": "ada@example.com"},
        {"email": "exists:users,email"},
    ).passes()
    assert validator(
        {"email": "missing@example.com"},
        {"email": "exists:users,email"},
    ).fails()

    assert validator(
        {"email": "new@example.com"},
        {"email": "unique:users,email"},
    ).passes()
    assert validator(
        {"email": "ada@example.com"},
        {"email": "unique:users,email"},
    ).fails()
