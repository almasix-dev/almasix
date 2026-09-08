"""M5 regression — public ORM contracts."""

from __future__ import annotations

import pytest

import almasix.orm as orm

pytestmark = pytest.mark.regression


def test_orm_exports() -> None:
    for name in (
        "Model",
        "QueryBuilder",
        "DB",
        "Schema",
        "Collection",
        "SoftDeletes",
        "Migration",
        "Migrator",
        "guess_migration",
        "SchemaError",
        "Seeder",
        "WithoutModelEvents",
        "HasMany",
        "BelongsTo",
        "BelongsToMany",
        "MorphTo",
        "Paginator",
        "relation",
    ):
        assert name in orm.__all__
        assert hasattr(orm, name)
