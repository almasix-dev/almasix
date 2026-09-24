"""Database notification persistence — Laravel-shaped ``notifications`` table."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any


def notifiable_type(notifiable: Any) -> str:
    """Morph type string for a notifiable (module + qualname)."""
    return f"{type(notifiable).__module__}.{type(notifiable).__qualname__}"


def notifiable_id(notifiable: Any) -> str:
    """Morph id string for a notifiable (``get_key()`` / ``id``)."""
    key = getattr(notifiable, "get_key", None)
    if callable(key):
        return str(key())
    return str(getattr(notifiable, "id", notifiable))


# Backward-compatible private aliases.
_notifiable_type = notifiable_type
_notifiable_id = notifiable_id


class DatabaseNotificationStore:
    """CRUD for Laravel-shaped ``notifications`` rows."""

    async def create(
        self,
        notifiable: Any,
        notification: Any,
        data: dict[str, Any],
        *,
        notification_id: str | None = None,
        notification_type: str | None = None,
    ) -> dict[str, Any]:
        from almasix.orm import DB

        row_id = notification_id or str(uuid.uuid4())
        now = datetime.now(UTC)
        type_name = notification_type or (
            f"{type(notification).__module__}.{type(notification).__qualname__}"
            if notification is not None
            else "notification"
        )
        payload = {
            "id": row_id,
            "type": type_name,
            "notifiable_type": notifiable_type(notifiable),
            "notifiable_id": notifiable_id(notifiable),
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
            .where("notifiable_type", notifiable_type(notifiable))
            .where("notifiable_id", notifiable_id(notifiable))
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

    async def mark_as_unread(self, notification_id: str) -> bool:
        from almasix.orm import DB

        now = datetime.now(UTC)
        affected = await (
            DB.table("notifications")
            .where("id", notification_id)
            .update({"read_at": None, "updated_at": now})
        )
        return bool(affected)

    async def mark_all_as_read(self, notifiable: Any) -> int:
        """Mark every unread notification for ``notifiable`` as read."""
        from almasix.orm import DB

        now = datetime.now(UTC)
        affected = await (
            DB.table("notifications")
            .where("notifiable_type", notifiable_type(notifiable))
            .where("notifiable_id", notifiable_id(notifiable))
            .where_null("read_at")
            .update({"read_at": now, "updated_at": now})
        )
        return int(affected or 0)

    async def find(self, notification_id: str) -> dict[str, Any] | None:
        from almasix.orm import DB

        row = await DB.table("notifications").where("id", notification_id).first()
        if row is None:
            return None
        item = dict(row)
        raw = item.get("data")
        if isinstance(raw, str):
            try:
                item["data"] = json.loads(raw)
            except json.JSONDecodeError:
                pass
        return item
