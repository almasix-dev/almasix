"""Embeds — the relation a document store has that a SQL database does not.

References (`has_many`, `belongs_to`, the morphs) work unchanged on documents:
they are key lookups, and a key lookup is a key lookup. What is new here is
the child that lives *inside* the parent document.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from almasix.orm.documents.model import EmbeddedDocument
from almasix.orm.model import Model


class EmbedsOne:
    """One embedded document, stored under a single field."""

    def __init__(self, parent: Model, related: type[EmbeddedDocument], field: str) -> None:
        self.parent = parent
        self.related = related
        self.field = field

    def get(self) -> EmbeddedDocument | None:
        """The embed as an object; `None` when the field is empty."""
        value = self.parent.get_raw_attribute(self.field)
        embed = self.related.hydrate(value)
        return embed.bind(self.parent, self.field) if embed else None

    def associate(self, value: EmbeddedDocument | Mapping[str, Any]) -> EmbeddedDocument:
        """Put an embed in place, without saving."""
        embed = self.related.hydrate(value)
        assert embed is not None  # hydrate only returns None for None
        self.parent.set_attribute(self.field, embed.to_dict())
        return embed.bind(self.parent, self.field)

    async def create(self, attributes: Mapping[str, Any] | None = None, **kwargs: Any) -> EmbeddedDocument:
        embed = self.associate({**(attributes or {}), **kwargs})
        await self.parent.save()
        return embed

    async def delete(self) -> bool:
        self.parent.set_attribute(self.field, None)
        return await self.parent.save()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<EmbedsOne {self.field} of {type(self.parent).__name__}>"


class EmbedsMany:
    """A list of embedded documents, stored under one array field."""

    def __init__(self, parent: Model, related: type[EmbeddedDocument], field: str) -> None:
        self.parent = parent
        self.related = related
        self.field = field

    def get(self) -> list[EmbeddedDocument]:
        values = self.parent.get_raw_attribute(self.field) or []
        return [
            embed.bind(self.parent, self.field, position)
            for position, embed in enumerate(self.related.hydrate_many(values))
        ]

    def _write(self, embeds: Iterable[EmbeddedDocument]) -> list[EmbeddedDocument]:
        listed = list(embeds)
        self.parent.set_attribute(self.field, [embed.to_dict() for embed in listed])
        return [
            embed.bind(self.parent, self.field, position)
            for position, embed in enumerate(listed)
        ]

    def associate(self, value: EmbeddedDocument | Mapping[str, Any]) -> EmbeddedDocument:
        """Append an embed, without saving."""
        embed = self.related.hydrate(value)
        assert embed is not None  # hydrate only returns None for None
        return self._write([*self.get(), embed])[-1]

    async def create(self, attributes: Mapping[str, Any] | None = None, **kwargs: Any) -> EmbeddedDocument:
        embed = self.associate({**(attributes or {}), **kwargs})
        await self.parent.save()
        return embed

    async def create_many(self, records: Iterable[Mapping[str, Any]]) -> list[EmbeddedDocument]:
        for record in records:
            self.associate(record)
        await self.parent.save()
        return self.get()

    def set(self, values: Iterable[EmbeddedDocument | Mapping[str, Any]]) -> list[EmbeddedDocument]:
        """Replace the whole list, without saving."""
        embeds = [self.related.hydrate(value) for value in values]
        return self._write([embed for embed in embeds if embed is not None])

    async def delete_where(self, **matching: Any) -> int:
        """Remove the embeds whose fields all match, then save the parent."""
        kept: list[EmbeddedDocument] = []
        removed = 0
        for embed in self.get():
            values = embed.to_dict()
            if all(values.get(key) == value for key, value in matching.items()):
                removed += 1
            else:
                kept.append(embed)
        if removed:
            self._write(kept)
            await self.parent.save()
        return removed

    def where(self, **matching: Any) -> list[EmbeddedDocument]:
        """Filter in memory — the embeds are already here, there is no query."""
        return [
            embed
            for embed in self.get()
            if all(embed.to_dict().get(key) == value for key, value in matching.items())
        ]

    def first(self) -> EmbeddedDocument | None:
        found = self.get()
        return found[0] if found else None

    def count(self) -> int:
        return len(self.parent.get_raw_attribute(self.field) or [])

    def __iter__(self) -> Any:
        return iter(self.get())

    def __len__(self) -> int:
        return self.count()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<EmbedsMany {self.field} of {type(self.parent).__name__}>"


def embeds_one(parent: Model, related: type[EmbeddedDocument], field: str | None = None) -> EmbedsOne:
    return EmbedsOne(parent, related, field or _guess_field(related))


def embeds_many(parent: Model, related: type[EmbeddedDocument], field: str | None = None) -> EmbedsMany:
    from almasix.support.str import Str

    return EmbedsMany(parent, related, field or Str.plural(_guess_field(related)))


def _guess_field(related: type[EmbeddedDocument]) -> str:
    from almasix.support.str import Str

    return Str.snake(related.__name__)
