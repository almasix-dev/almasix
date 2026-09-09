"""Eager loading for documents.

Reference relations are key lookups, so the SQL loader already works: it asks
the relation for a builder and the relation asks the model, which hands back a
`DocumentBuilder`. Counting is the one thing that needs its own path, because
SQL counts with `GROUP BY` and a store counts with whatever it has.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from almasix.orm.eager import eager_load


async def load_document_relations(
    models: Sequence[Any], relations: Mapping[str, Any] | Any
) -> None:
    """Load reference relations onto documents — one query per relation."""
    await eager_load(models, relations)


async def load_document_counts(models: Sequence[Any], relation_name: str, alias: str) -> None:
    """Attach `{relation}_count` by grouping in the store."""
    relation = models[0].get_relation(relation_name)
    builder = relation.eager_query(models)
    grouping = builder.field(relation.grouping_column())
    counts = await builder.get_store().group_count(builder.to_query(), grouping)
    parent_key = relation.parent_match_key()
    for model in models:
        model._extra[alias] = int(counts.get(model.get_raw_attribute(parent_key), 0) or 0)


def is_document(model: Any) -> bool:
    """Whether a model class stores its rows in a document store."""
    return bool(getattr(model, "_is_document", False))
