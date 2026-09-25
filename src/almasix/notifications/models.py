"""``DatabaseNotification`` model — one row in the ``notifications`` table."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, ClassVar

from almasix.orm import Model


class DatabaseNotification(Model):
    """Laravel-shaped inbox row (UUID primary key, morph notifiable, JSON data)."""

    table: ClassVar[str | None] = "notifications"
    primary_key: ClassVar[str] = "id"
    key_type: ClassVar[str] = "string"
    incrementing: ClassVar[bool] = False
    timestamps: ClassVar[bool] = True

    fillable = (
        "id",
        "type",
        "notifiable_type",
        "notifiable_id",
        "data",
        "read_at",
    )

    def get_data(self) -> dict[str, Any]:
        raw = getattr(self, "data", None)
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def is_read(self) -> bool:
        return getattr(self, "read_at", None) is not None

    def is_unread(self) -> bool:
        return not self.is_read()

    async def mark_as_read(self) -> bool:
        if self.is_read():
            return True
        now = datetime.now(UTC)
        self.read_at = now
        return await self.save()

    async def mark_as_unread(self) -> bool:
        if self.is_unread():
            return True
        self.read_at = None
        return await self.save()
