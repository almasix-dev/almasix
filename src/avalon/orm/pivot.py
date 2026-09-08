"""Intermediate table models — Laravel's `Pivot` and `MorphPivot`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from avalon.orm.model import Model


class Pivot(Model):
    """A row of a many-to-many intermediate table.

    Pivot tables rarely carry their own key, so incrementing is off and writes
    are keyed on the pair of foreign keys through the owning relation.
    """

    table = "pivot"
    incrementing: ClassVar[bool] = False
    timestamps: ClassVar[bool] = False
    guarded: ClassVar[tuple[str, ...]] = ()

    def get_pivot_table(self) -> str:
        """The intermediate table this row came from."""
        return self.__dict__.get("_pivot_table") or type(self).get_table()

    # --- writes -------------------------------------------------------------

    async def save(self, **kwargs: Any) -> Any:
        """Persist changed pivot columns through the owning relation."""
        relation = self.__dict__.get("_relation")
        if relation is None:
            return await super().save(**kwargs)
        skip = (relation.foreign_pivot_key, relation.related_pivot_key)
        changed = {
            key: value for key, value in self.get_attributes().items() if key not in skip
        }
        await relation.update_existing_pivot(self._related_id(relation), changed)
        self.sync_original()
        return self

    async def delete(self) -> Any:
        relation = self.__dict__.get("_relation")
        if relation is None:
            return await super().delete()
        return await relation.detach(self._related_id(relation))

    def _related_id(self, relation: Any) -> Any:
        return self.get_raw_attribute(relation.related_pivot_key)


class MorphPivot(Pivot):
    """A pivot row on a polymorphic intermediate table."""


def new_pivot(
    relation: Any,
    attributes: Mapping[str, Any],
    *,
    exists: bool = True,
) -> Pivot:
    """Build the pivot instance a relation attaches to its results."""
    instance = relation.pivot_class()
    instance.__dict__["_pivot_table"] = relation.pivot
    instance.__dict__["_relation"] = relation
    instance.force_fill(dict(attributes))
    instance._exists = exists
    instance.sync_original()
    return instance
