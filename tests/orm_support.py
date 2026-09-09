"""Shared database fixture for ORM tests.

Defaults to SQLite ``:memory:`` so the local suite stays offline. Point
``ALMASIX_TEST_DB`` at ``pgsql``, ``mysql``, or ``mariadb`` (and fill the
usual ``DB_*`` env vars) to run the same fixtures against a real engine —
what CI does for the multi-engine conformance job.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Mapping
from typing import Any

import pytest

from almasix.orm import DatabaseManager, Schema, set_manager
from almasix.orm.model import Model

# Engines the suite can execute against today. SQL Server / Oracle stay
# compile-only until a service is wired (see docs/PLAN.md M44).
EXECUTABLE_ENGINES = ("sqlite", "pgsql", "mysql", "mariadb")


def test_engine() -> str:
    """Which engine the ORM fixtures should open."""
    raw = os.environ.get("ALMASIX_TEST_DB", "sqlite").strip().lower()
    aliases = {
        "postgres": "pgsql",
        "postgresql": "pgsql",
        "pg": "pgsql",
        "mariadb": "mariadb",
    }
    engine = aliases.get(raw, raw)
    if engine not in EXECUTABLE_ENGINES:
        raise ValueError(
            f"ALMASIX_TEST_DB={raw!r} is not executable; "
            f"choose one of {', '.join(EXECUTABLE_ENGINES)}"
        )
    return engine


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def connection_config(engine: str | None = None) -> dict[str, Any]:
    """Laravel-shaped connection dict for the active test engine."""
    name = engine or test_engine()
    if name == "sqlite":
        return {"driver": "sqlite", "database": ":memory:"}
    if name == "pgsql":
        return {
            "driver": "pgsql",
            "host": _env("DB_HOST", "127.0.0.1"),
            "port": int(_env("DB_PORT", "5432")),
            "database": _env("DB_DATABASE", "almasix_test"),
            "username": _env("DB_USERNAME", "almasix"),
            "password": _env("DB_PASSWORD", "secret"),
        }
    # mysql / mariadb share aiomysql; only the driver label differs.
    return {
        "driver": name,
        "host": _env("DB_HOST", "127.0.0.1"),
        "port": int(_env("DB_PORT", "3306")),
        "database": _env("DB_DATABASE", "almasix_test"),
        "username": _env("DB_USERNAME", "almasix"),
        "password": _env("DB_PASSWORD", "secret"),
    }


def manager_config(engine: str | None = None) -> dict[str, Any]:
    name = engine or test_engine()
    return {
        "default": name,
        "connections": {name: connection_config(name)},
    }


@pytest.fixture
async def memory_db() -> AsyncIterator[DatabaseManager]:
    """Bind the facade to the active test engine for one test.

    Named ``memory_db`` for historical reasons — SQLite still uses
    ``:memory:``. Server engines get a clean slate via ``drop_all_tables``.
    """
    engine = test_engine()
    manager = DatabaseManager(manager_config(engine))
    set_manager(manager)
    if engine != "sqlite":
        await Schema.drop_all_tables()
    try:
        yield manager
    finally:
        if engine != "sqlite":
            await Schema.drop_all_tables()
        await manager.disconnect()
        set_manager(None)


async def create_tables(*callbacks) -> None:
    for table, callback in callbacks:
        await Schema.create(table, callback)


def reset_model(cls: type[Model]) -> None:
    cls._events = {event: [] for event in cls._events}
    cls._global_scopes = dict(cls._global_scopes)


def requires_engine(*engines: str) -> pytest.MarkDecorator:
    """Skip unless ``ALMASIX_TEST_DB`` is one of ``engines``."""
    wanted = {aliases(e) for e in engines}
    return pytest.mark.skipif(
        test_engine() not in wanted,
        reason=f"needs ALMASIX_TEST_DB in {{{', '.join(sorted(wanted))}}}",
    )


def skip_on_engine(*engines: str) -> pytest.MarkDecorator:
    """Skip when the active engine is one of ``engines``."""
    blocked = {aliases(e) for e in engines}
    return pytest.mark.skipif(
        test_engine() in blocked,
        reason=f"not supported on {test_engine()}",
    )


def aliases(name: str) -> str:
    mapping = {
        "postgres": "pgsql",
        "postgresql": "pgsql",
        "pg": "pgsql",
    }
    return mapping.get(name, name)


def engine_capabilities() -> Mapping[str, bool]:
    """What the active engine can honestly claim at runtime."""
    engine = test_engine()
    return {
        "native_upsert": engine in {"sqlite", "pgsql", "mysql", "mariadb"},
        "json_path_wheres": True,
        "row_locks": engine != "sqlite",
        "transactional_ddl": engine == "pgsql",
        "change_column": engine != "sqlite",
        "drop_foreign": engine != "sqlite",
    }
