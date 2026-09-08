"""Shared in-memory SQLite for ORM tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from almasix.orm import DatabaseManager, Schema, set_manager
from almasix.orm.model import Model


@pytest.fixture
async def memory_db() -> AsyncIterator[DatabaseManager]:
    manager = DatabaseManager(
        {
            "default": "sqlite",
            "connections": {"sqlite": {"driver": "sqlite", "database": ":memory:"}},
        }
    )
    set_manager(manager)
    yield manager
    await manager.disconnect()
    set_manager(None)


async def create_tables(*callbacks) -> None:
    for table, callback in callbacks:
        await Schema.create(table, callback)


def reset_model(cls: type[Model]) -> None:
    cls._events = {event: [] for event in cls._events}
    cls._global_scopes = dict(cls._global_scopes)
