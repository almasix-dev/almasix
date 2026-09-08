"""The relationship helpers behind `has`, `has_attached`, and `for_`."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from almasix.orm.collection import Collection
from almasix.orm.model import Model
from almasix.orm.morph import morph_alias
from almasix.orm.relations import (
    BelongsTo,
    BelongsToMany,
    HasOneOrMany,
    MorphOneOrMany,
    MorphTo,
)


class RelationshipError(RuntimeError):
    """A factory was pointed at something that is not a usable relation."""


def _as_models(value: Any) -> list[Model]:
    if isinstance(value, Model):
        return [value]
    if isinstance(value, (Collection, list, tuple, set)):
        return [item for item in value if isinstance(item, Model)]
    return []


class Relationship:
    """A child factory attached with `has()` — created after the parent is."""

    def __init__(self, factory: Any, relationship: str) -> None:
        self.factory = factory
        self.relationship = relationship

    def recycle(self, models: Mapping[type[Model], list[Model]]) -> Relationship:
        return type(self)(self.factory.recycle(models), self.relationship)

    async def create_for(self, parent: Model) -> None:
        relation = parent.get_relation(self.relationship)
        if isinstance(relation, MorphOneOrMany):
            state = {
                relation.foreign_key: parent.get_raw_attribute(relation.local_key),
                relation.morph_type: relation.morph_class,
            }
            await self.factory.state(state).create(parent=parent)
        elif isinstance(relation, HasOneOrMany):
            state = {relation.foreign_key: parent.get_raw_attribute(relation.local_key)}
            await self.factory.state(state).create(parent=parent)
        elif isinstance(relation, BelongsToMany):
            created = await self.factory.create(parent=parent)
            await relation.attach(created)
        else:
            raise RelationshipError(
                f"{type(parent).__name__}.{self.relationship} is a "
                f"{type(relation).__name__}; has() needs a has-many, morph-many, "
                "or belongs-to-many relation"
            )


class BelongsToManyRelationship:
    """Children attached with `has_attached()`, pivot columns and all."""

    def __init__(
        self,
        factory: Any,
        pivot: Mapping[str, Any] | Callable[[Model], Mapping[str, Any]] | None,
        relationship: str,
    ) -> None:
        self.factory = factory
        self.pivot = pivot or {}
        self.relationship = relationship

    def recycle(self, models: Mapping[type[Model], list[Model]]) -> BelongsToManyRelationship:
        factory = self.factory.recycle(models) if hasattr(self.factory, "recycle") else self.factory
        return type(self)(factory, self.pivot, self.relationship)

    async def create_for(self, parent: Model) -> None:
        relation = parent.get_relation(self.relationship)
        if not isinstance(relation, BelongsToMany):
            raise RelationshipError(
                f"{type(parent).__name__}.{self.relationship} is a "
                f"{type(relation).__name__}; has_attached() needs a belongs-to-many relation"
            )
        models = _as_models(self.factory)
        if not models:
            models = _as_models(await self.factory.create(parent=parent))
        for model in models:
            pivot = self.pivot(model) if callable(self.pivot) else dict(self.pivot)
            await relation.attach(model, pivot)


class BelongsToRelationship:
    """A parent supplied with `for_()` — resolved before the child is made."""

    def __init__(self, factory: Any, relationship: str) -> None:
        self.factory = factory
        self.relationship = relationship
        self._resolved: Model | None = None
        self._recycled = False

    def recycle(self, models: Mapping[type[Model], list[Model]]) -> BelongsToRelationship:
        """Keep one object per `for_()` so a batch of children shares one parent."""
        if models and not self._recycled and not isinstance(self.factory, Model):
            self.factory = self.factory.recycle(models)
            self._recycled = True
        return self

    async def _resolve(self) -> Model:
        if isinstance(self.factory, Model):
            return self.factory
        if self._resolved is None:
            recycled = self.factory.get_random_recycled_model(self.factory.model_name())
            self._resolved = recycled or await self.factory.create()
        return self._resolved

    async def attributes_for(self, child: Model) -> dict[str, Any]:
        relation = child.get_relation(self.relationship)
        parent = await self._resolve()
        if isinstance(relation, MorphTo):
            return {
                relation.morph_id: parent.get_key(),
                relation.morph_type: morph_alias(type(parent)),
            }
        if isinstance(relation, BelongsTo):
            return {relation.foreign_key: parent.get_raw_attribute(relation.owner_key)}
        raise RelationshipError(
            f"{type(child).__name__}.{self.relationship} is a "
            f"{type(relation).__name__}; for_() needs a belongs-to or morph-to relation"
        )


def merge_recycled(
    pool: Mapping[type[Model], list[Model]],
    models: Iterable[Model] | Model | None,
) -> dict[type[Model], list[Model]]:
    """Add models to the recycle pool, keyed by their class."""
    merged: dict[type[Model], list[Model]] = {key: list(value) for key, value in pool.items()}
    for model in _as_models(models):
        merged.setdefault(type(model), []).append(model)
    return merged
