"""Search engines — the drivers behind `scout.driver`."""

from __future__ import annotations

from almasix.scout.engines.base import Engine, hydrate, searchable_payload
from almasix.scout.engines.collection import CollectionEngine
from almasix.scout.engines.database import DatabaseEngine
from almasix.scout.engines.meilisearch import MeilisearchEngine
from almasix.scout.engines.null import NullEngine

__all__ = [
    "CollectionEngine",
    "DatabaseEngine",
    "Engine",
    "MeilisearchEngine",
    "NullEngine",
    "hydrate",
    "searchable_payload",
]
