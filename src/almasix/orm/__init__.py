"""Eloquent-like ORM over SQLAlchemy Core (async-first)."""

from almasix.orm.attributes import Attribute, attribute
from almasix.orm.builder import ModelNotFoundError, QueryBuilder
from almasix.orm.casts import (
    CastError,
    CastsAttributes,
    CastsInboundAttributes,
    EnumCollection,
)
from almasix.orm.collection import Collection
from almasix.orm.connection import Connection, DatabaseManager
from almasix.orm.facade import DB, get_manager, raw, set_manager
from almasix.orm.factories import (
    CrossJoinSequence,
    Factory,
    FactoryError,
    Fake,
    HasFactory,
    Sequence,
    fake,
)
from almasix.orm.ids import HasUlids, HasUniqueStringIds, HasUuids, ordered_uuid, ulid
from almasix.orm.migration import Migration, Migrator, guess_migration, make_migration
from almasix.orm.model import (
    DiscardedAttributeError,
    MassAssignmentError,
    MissingAttributeError,
    Model,
    RelationNotLoadedError,
    relation,
)
from almasix.orm.morph import (
    clear_morph_map,
    enforce_morph_map,
    morph_alias,
    morph_map,
)
from almasix.orm.pagination import Paginator, SimplePaginator
from almasix.orm.pivot import MorphPivot, Pivot
from almasix.orm.provider import DatabaseServiceProvider
from almasix.orm.pruning import MassPrunable, Prunable
from almasix.orm.relations import (
    BelongsTo,
    BelongsToMany,
    HasMany,
    HasManyThrough,
    HasOne,
    HasOneThrough,
    MorphMany,
    MorphOne,
    MorphTo,
    MorphToMany,
    Relation,
)
from almasix.orm.schema import Blueprint, Schema, SchemaError
from almasix.orm.seeder import (
    Seeder,
    SeederError,
    WithoutModelEvents,
    invoke_seeder,
    load_database_seeder,
    make_seeder,
    reset_called,
    resolve_seeder_class,
    run_seeder,
    without_model_events,
)
from almasix.orm.soft_deletes import SoftDeletes

__all__ = [
    "DB",
    "Attribute",
    "BelongsTo",
    "BelongsToMany",
    "Blueprint",
    "CastError",
    "CastsAttributes",
    "CastsInboundAttributes",
    "Collection",
    "Connection",
    "CrossJoinSequence",
    "DatabaseManager",
    "DatabaseServiceProvider",
    "DiscardedAttributeError",
    "EnumCollection",
    "Factory",
    "FactoryError",
    "Fake",
    "HasFactory",
    "HasMany",
    "HasManyThrough",
    "HasOne",
    "HasOneThrough",
    "HasUlids",
    "HasUniqueStringIds",
    "HasUuids",
    "MassAssignmentError",
    "MassPrunable",
    "Migration",
    "Migrator",
    "MissingAttributeError",
    "Model",
    "ModelNotFoundError",
    "MorphMany",
    "MorphOne",
    "MorphPivot",
    "MorphTo",
    "MorphToMany",
    "Paginator",
    "Pivot",
    "Prunable",
    "QueryBuilder",
    "Relation",
    "RelationNotLoadedError",
    "Schema",
    "SchemaError",
    "Seeder",
    "SeederError",
    "Sequence",
    "SimplePaginator",
    "SoftDeletes",
    "WithoutModelEvents",
    "attribute",
    "clear_morph_map",
    "enforce_morph_map",
    "fake",
    "get_manager",
    "guess_migration",
    "invoke_seeder",
    "load_database_seeder",
    "make_migration",
    "make_seeder",
    "morph_alias",
    "morph_map",
    "ordered_uuid",
    "raw",
    "relation",
    "reset_called",
    "resolve_seeder_class",
    "run_seeder",
    "set_manager",
    "ulid",
    "without_model_events",
]
