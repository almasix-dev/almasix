"""Document models — Articulate, with a collection underneath instead of a table.

A `Document` is a `Model`: the same attributes, casts, accessors, mutators,
dirty tracking, events, observers, serialization, and soft deletes. What
changes is where a row goes, so only the query and persistence seam is
overridden here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from almasix.orm.documents.builder import DocumentBuilder
from almasix.orm.documents.filters import UnsupportedQueryError
from almasix.orm.model import Model


class Document(Model):
    """A model whose rows are documents in a collection.

    class Article(Document):
        connection = "mongodb"
        collection = "articles"
        fillable = ("title", "body", "tags")
    """

    #: Marks the whole class tree for the parts of Articulate that must know.
    _is_document: ClassVar[bool] = True

    #: The collection name; guessed from the class name when unset.
    collection: ClassVar[str | None] = None

    primary_key: ClassVar[str] = "_id"
    incrementing: ClassVar[bool] = False
    key_type: ClassVar[str] = "string"

    #: Indexes this collection wants, as `smith documents:index` creates them.
    indexes: ClassVar[tuple[Mapping[str, Any], ...]] = ()

    # --- naming -------------------------------------------------------------

    @classmethod
    def get_table(cls) -> str:
        """The collection name — `table` stays as an alias, so seeders read the same."""
        if cls.collection:
            return cls.collection
        return super().get_table()

    @classmethod
    def get_collection(cls) -> str:
        return cls.get_table()

    # --- queries ------------------------------------------------------------

    @classmethod
    def query(cls) -> DocumentBuilder:
        builder = DocumentBuilder(model=cls, connection=cls.connection)
        if cls.with_:
            builder.with_(*cls.with_)
        return builder

    @classmethod
    def new_query(cls) -> DocumentBuilder:
        return DocumentBuilder(model=cls, connection=cls.connection)

    @classmethod
    def on(cls, connection: str | None) -> DocumentBuilder:
        return DocumentBuilder(model=cls, connection=connection)

    def instance_query(self) -> DocumentBuilder:
        return DocumentBuilder(model=type(self), connection=self.get_connection_name())

    @classmethod
    def get_store(cls, connection: str | None = None) -> Any:
        from almasix.orm.facade import get_manager

        return get_manager().store(connection or cls.connection)

    # --- persistence --------------------------------------------------------

    async def _perform_insert(self) -> bool:
        if await self._fire_event("creating") is False:
            return False
        from almasix.orm.ids import fill_unique_ids

        fill_unique_ids(self)
        self._touch_timestamps(creating=True)

        cls = type(self)
        payload = dict(self._attributes)
        if payload.get(cls.primary_key) is None:
            payload.pop(cls.primary_key, None)

        key = await self.instance_query().insert_get_id(payload)
        self._attributes[cls.primary_key] = key
        self._exists = True
        self._changes = dict(self._attributes)
        self.sync_original()
        await self._fire_event("created")
        return True

    # --- embedded relations -------------------------------------------------

    def embeds_one(self, related: type[EmbeddedDocument], field: str | None = None) -> Any:
        """One embedded document, living inside this one."""
        from almasix.orm.documents.relations import embeds_one

        return embeds_one(self, related, field)

    def embeds_many(self, related: type[EmbeddedDocument], field: str | None = None) -> Any:
        """A list of embedded documents, living inside this one."""
        from almasix.orm.documents.relations import embeds_many

        return embeds_many(self, related, field)

    # --- indexes ------------------------------------------------------------

    @classmethod
    async def sync_indexes(cls) -> list[str]:
        """Create every index the model declares; returns their names.

        indexes = ({"keys": [("email", 1)], "unique": True},)
        """
        store = cls.get_store()
        created: list[str] = []
        for index in cls.indexes:
            keys = [(field, int(direction)) for field, direction in index["keys"]]
            created.append(
                await store.create_index(
                    cls.get_table(),
                    keys,
                    unique=bool(index.get("unique", False)),
                    name=index.get("name"),
                )
            )
        return created

    # --- what a document store will not do ----------------------------------

    @classmethod
    def where_column(cls, *args: Any, **kwargs: Any) -> Any:
        raise UnsupportedQueryError(
            "where_column() is SQL-only — compare two fields with raw_aggregate() and $expr"
        )


class EmbeddedDocument:
    """A document stored inside another one, not in a collection of its own.

    Embeds carry no key and no table; they are values with behaviour, which is
    what makes them worth having over a bare dict.
    """

    #: Attributes an embed accepts; empty means anything.
    fields: ClassVar[tuple[str, ...]] = ()

    def __init__(self, attributes: Mapping[str, Any] | None = None, **kwargs: Any) -> None:
        payload = {**(attributes or {}), **kwargs}
        if self.fields:
            unknown = set(payload) - set(self.fields)
            if unknown:
                raise ValueError(
                    f"{type(self).__name__} has no field(s) {', '.join(sorted(unknown))}"
                )
        self._attributes: dict[str, Any] = dict(payload)
        self._parent: Model | None = None
        self._relation: str | None = None
        self._position: int | None = None

    # --- attribute access ---------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        attributes = self.__dict__.get("_attributes", {})
        if name in attributes:
            return attributes[name]
        raise AttributeError(f"{type(self).__name__!r} has no attribute {name!r}")

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_") or name in type(self).__dict__ or hasattr(type(self), name):
            object.__setattr__(self, name, value)
            return
        self._attributes[name] = value

    def __getitem__(self, key: str) -> Any:
        return self._attributes[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._attributes[key] = value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, EmbeddedDocument) and self.to_dict() == other.to_dict()

    def __hash__(self) -> int:  # pragma: no cover - embeds are compared, not keyed
        return hash(tuple(sorted(self._attributes)))

    def fill(self, attributes: Mapping[str, Any]) -> EmbeddedDocument:
        self._attributes.update(dict(attributes))
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            key: value.to_dict() if isinstance(value, EmbeddedDocument) else value
            for key, value in self._attributes.items()
        }

    def bind(self, parent: Model, relation: str, position: int | None = None) -> EmbeddedDocument:
        """Remember where this embed lives, so `save()` can write it back.

        `position` is the index inside an array field; `None` means the embed
        is the whole value of the field.
        """
        self._parent = parent
        self._relation = relation
        self._position = position
        return self

    async def save(self) -> bool:
        """Write this embed back into its parent, then save the parent."""
        if self._parent is None or self._relation is None:
            raise UnsupportedQueryError(
                f"This {type(self).__name__} is not embedded in anything yet"
            )
        if self._position is None:
            self._parent.set_attribute(self._relation, self.to_dict())
        else:
            values = list(self._parent.get_raw_attribute(self._relation) or [])
            values[self._position] = self.to_dict()
            self._parent.set_attribute(self._relation, values)
        return await self._parent.save()

    @classmethod
    def hydrate(cls, value: Mapping[str, Any] | EmbeddedDocument | None) -> EmbeddedDocument | None:
        if value is None:
            return None
        if isinstance(value, EmbeddedDocument):
            return value
        return cls(dict(value))

    @classmethod
    def hydrate_many(cls, values: Sequence[Any] | None) -> list[EmbeddedDocument]:
        return [embed for embed in (cls.hydrate(value) for value in values or []) if embed]

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} {self._attributes!r}>"
