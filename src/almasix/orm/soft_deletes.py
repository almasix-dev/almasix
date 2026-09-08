"""Soft deletes — `deleted_at` global scope plus restore/force-delete."""

from __future__ import annotations

from typing import Any, ClassVar

from almasix.orm.builder import QueryBuilder

SOFT_DELETE_SCOPE = "soft_deletes"


class SoftDeletes:
    """Mixin: excludes trashed rows unless explicitly asked for.

    Mix in **before** `Model` so the metaclass picks up the global scope::

        class Post(SoftDeletes, Model):
            ...
    """

    deleted_at: ClassVar[str] = "deleted_at"
    _soft_deletes: ClassVar[bool] = True

    @staticmethod
    def boot_soft_deletes(cls: Any) -> None:
        column = getattr(cls, "deleted_at", "deleted_at")

        def scope(builder: QueryBuilder) -> None:
            builder.where_null(f"{builder.table}.{column}")

        cls.add_global_scope(SOFT_DELETE_SCOPE, scope)

    # --- query entrypoints --------------------------------------------------

    @classmethod
    def with_trashed(cls) -> QueryBuilder:
        return cls.query().without_global_scope(SOFT_DELETE_SCOPE)  # type: ignore[attr-defined]

    @classmethod
    def only_trashed(cls) -> QueryBuilder:
        builder = cls.query().without_global_scope(SOFT_DELETE_SCOPE)  # type: ignore[attr-defined]
        return builder.where_not_null(f"{builder.table}.{cls.deleted_at}")

    @classmethod
    def without_trashed(cls) -> QueryBuilder:
        """The default scope, stated explicitly (``withoutTrashed``)."""
        return cls.query()  # type: ignore[attr-defined]

    # --- instance -----------------------------------------------------------

    def trashed(self) -> bool:
        return self.get_raw_attribute(type(self).deleted_at) is not None  # type: ignore[attr-defined]

    async def _perform_soft_delete(self) -> bool:
        cls = type(self)
        stamp = self._fresh_timestamp()  # type: ignore[attr-defined]
        await (
            cls.new_query()  # type: ignore[attr-defined]
            .without_global_scopes()
            .where(cls.primary_key, "=", self.get_key())  # type: ignore[attr-defined]
            .update({cls.deleted_at: stamp})
        )
        self._attributes[cls.deleted_at] = stamp  # type: ignore[attr-defined]
        self.sync_original()  # type: ignore[attr-defined]
        return True

    async def restore(self) -> bool:
        cls = type(self)
        if await self._fire_event("restoring") is False:  # type: ignore[attr-defined]
            return False
        await (
            cls.new_query()  # type: ignore[attr-defined]
            .without_global_scopes()
            .where(cls.primary_key, "=", self.get_key())  # type: ignore[attr-defined]
            .update({cls.deleted_at: None})
        )
        self._attributes[cls.deleted_at] = None  # type: ignore[attr-defined]
        self.sync_original()  # type: ignore[attr-defined]
        await self._fire_event("restored")  # type: ignore[attr-defined]
        return True

    async def restore_quietly(self) -> bool:
        """Restore without firing model events (``restoreQuietly``)."""
        return await self._quietly(self.restore)  # type: ignore[attr-defined]
