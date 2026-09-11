"""Notification inbox shell."""

from __future__ import annotations

from almasix.auth import auth
from almasix.http import Controller, Request, redirect
from inertia import Inertia


class NotificationController(Controller):
    async def index(self, request: Request):
        user = auth().user()
        items = []
        if user is not None and hasattr(user, "notifications"):
            try:
                rows = await user.notifications().limit(50).get()  # type: ignore[attr-defined]
                for row in rows:
                    items.append(
                        {
                            "id": str(row.get_key()),
                            "data": row.get_attribute("data") if hasattr(row, "get_attribute") else {},
                            "read_at": str(row.get_attribute("read_at") or "")
                            if hasattr(row, "get_attribute")
                            else "",
                        }
                    )
            except Exception:
                items = []
        return Inertia.render(
            "Notifications/Index",
            {"notifications": items, "status": request.session.get("status")},
        )

    async def mark_all(self, request: Request):
        user = auth().user()
        if user is not None and hasattr(user, "unread_notifications"):
            try:
                await user.unread_notifications().update({"read_at": __import__("almasix.support.helpers", fromlist=["now"]).now()})  # type: ignore[attr-defined]
            except Exception:
                pass
        request.session.flash("status", "All notifications marked as read.")
        return redirect("/notifications")
