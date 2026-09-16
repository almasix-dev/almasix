"""Email verification notice + signed verify (Inertia)."""

from __future__ import annotations

from almasix.auth import auth
from almasix.http import Controller, Request, redirect
from almasix.notifications.verification import mark_verified_from_request
from inertia import Inertia


class VerificationController(Controller):
    async def notice(self, request: Request):
        user = auth().user()
        return Inertia.render(
            "Auth/VerifyEmail",
            {
                "status": request.session.get("status"),
                "email": user.get_attribute("email") if user and hasattr(user, "get_attribute") else None,
            },
        )

    async def verify(self, request: Request, id: str, hash: str):
        expires = str(request.query("expires") or "")
        signature = str(request.query("signature") or "")
        from app.models.user import User

        user = await mark_verified_from_request(
            user_id=id,
            email_hash=hash,
            expires=expires,
            signature=signature,
            user_model=User,
        )
        if user is None:
            request.session.flash("errors", {"email": ["Invalid or expired verification link."]})
            return redirect("/email/verify")
        request.session.flash("status", "Email verified.")
        return redirect("/dashboard")

    async def resend(self, request: Request):
        user = auth().user()
        if user is None:
            return redirect("/login")
        sender = getattr(user, "send_email_verification_notification", None)
        if callable(sender):
            result = sender()
            if hasattr(result, "__await__"):
                await result  # type: ignore[misc]
        request.session.flash("status", "Verification link sent.")
        return redirect("/email/verify")
