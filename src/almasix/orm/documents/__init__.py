"""Document stores in Articulate — the same DX, over collections."""

from almasix.orm.documents.builder import SQL_ONLY, DocumentBuilder
from almasix.orm.documents.eager import (
    is_document,
    load_document_counts,
    load_document_relations,
)
from almasix.orm.documents.filters import (
    Condition,
    Order,
    Query,
    UnsupportedQueryError,
    dotted,
)
from almasix.orm.documents.model import Document, EmbeddedDocument
from almasix.orm.documents.relations import EmbedsMany, EmbedsOne
from almasix.orm.documents.stores import (
    DocumentStore,
    MemoryStore,
    MongoNotInstalled,
    MongoStore,
)

__all__ = [
    "SQL_ONLY",
    "Condition",
    "Document",
    "DocumentBuilder",
    "DocumentStore",
    "EmbeddedDocument",
    "EmbedsMany",
    "EmbedsOne",
    "MemoryStore",
    "MongoNotInstalled",
    "MongoStore",
    "Order",
    "Query",
    "UnsupportedQueryError",
    "dotted",
    "is_document",
    "load_document_counts",
    "load_document_relations",
]
