"""Email verification notice + signed verify endpoint (progress demo)."""

from __future__ import annotations

from almasix.auth import auth
from almasix.prism import view
from almasix.http import Controller, Request, Response, redirect
from almasix.notifications.verification import mark_verified_from_request
from almasix.routing import url


class VerificationController(Controller):
    async def notice(self) -> Response:
        user = auth().user()
        return view(
            "auth.verify_email",
            {
                "home_url": url("/", absolute=False),
                "resend_url": url("/email/verification-notification", absolute=False),
                "email": getattr(user, "email", None) if user else None,
            },
        )

    async def verify(
        self,
        request: Request,
        id: str,
        hash: str,
    ) -> Response:
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
            request.session.flash("error", "Invalid or expired verification link.")
            return redirect("/email/verify")
        request.session.flash("status", "Email verified.")
        return redirect("/")

    async def resend(self, request: Request) -> Response:
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
