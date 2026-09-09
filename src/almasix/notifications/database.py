"""Database notification persistence."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any


def _notifiable_type(notifiable: Any) -> str:
    return f"{type(notifiable).__module__}.{type(notifiable).__qualname__}"


def _notifiable_id(notifiable: Any) -> str:
    key = getattr(notifiable, "get_key", None)
    if callable(key):
        return str(key())
    return str(getattr(notifiable, "id", notifiable))


class DatabaseNotificationStore:
    """CRUD for Laravel-shaped ``notifications`` rows."""

    async def create(
        self,
        notifiable: Any,
        notification: Any,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        from almasix.orm import DB

        row_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        payload = {
            "id": row_id,
            "type": f"{type(notification).__module__}.{type(notification).__qualname__}",
            "notifiable_type": _notifiable_type(notifiable),
            "notifiable_id": _notifiable_id(notifiable),
            "data": json.dumps(data),
            "read_at": None,
            "created_at": now,
            "updated_at": now,
        }
        await DB.table("notifications").insert(payload)
        return {**payload, "data": data}

    async def for_notifiable(
        self,
        notifiable: Any,
        *,
        unread_only: bool = False,
    ) -> list[dict[str, Any]]:
        from almasix.orm import DB

        query = (
            DB.table("notifications")
            .where("notifiable_type", _notifiable_type(notifiable))
            .where("notifiable_id", _notifiable_id(notifiable))
            .order_by("created_at", "desc")
        )
        if unread_only:
            query = query.where_null("read_at")
        rows = await query.get()
        results: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            raw = item.get("data")
            if isinstance(raw, str):
                try:
                    item["data"] = json.loads(raw)
                except json.JSONDecodeError:
                    pass
            results.append(item)
        return results

    async def mark_as_read(self, notification_id: str) -> bool:
        from almasix.orm import DB

        now = datetime.now(UTC)
        affected = await (
            DB.table("notifications")
            .where("id", notification_id)
            .update({"read_at": now, "updated_at": now})
        )
        return bool(affected)
