"""Built-in notification messages (password reset, verify email)."""

from __future__ import annotations

from typing import Any

from almasix.mail.mailable import Content, Envelope, Mailable
from almasix.notifications.notification import Notification


class ResetPasswordNotification(Notification):
    """Password reset link notification (mail + optional log)."""

    def __init__(self, token: str, *, reset_url: str | None = None) -> None:
        self.token = token
        self.reset_url = reset_url

    def via(self, notifiable: Any) -> list[str]:
        del notifiable
        return ["mail"]

    def to_mail(self, notifiable: Any) -> Mailable:
        email = getattr(notifiable, "email", "") or ""
        if self.reset_url:
            url = self.reset_url
        else:
            try:
                from almasix.config import config

                base = str(config("app.url") or "").rstrip("/")
            except Exception:
                base = ""
            url = f"{base}/password/reset/{self.token}?email={email}"

        class ResetMail(Mailable):
            def envelope(self) -> Envelope:
                return Envelope(subject="Reset Password Notification")

            def content(self) -> Content:
                return Content(
                    text=(
                        "You are receiving this email because we received a password "
                        "reset request for your account.\n\n"
                        f"Reset Password: {url}\n\n"
                        "If you did not request a password reset, no further action "
                        "is required."
                    ),
                    html=(
                        "<p>You are receiving this email because we received a password "
                        "reset request for your account.</p>"
                        f'<p><a href="{url}">Reset Password</a></p>'
                        "<p>If you did not request a password reset, no further action "
                        "is required.</p>"
                    ),
                )

        return ResetMail()

    def to_array(self, notifiable: Any) -> dict[str, Any]:
        return {
            "token": self.token,
            "email": getattr(notifiable, "email", None),
            "reset_url": self.reset_url,
        }


class VerifyEmailNotification(Notification):
    """Email verification notification."""

    def via(self, notifiable: Any) -> list[str]:
        del notifiable
        return ["mail"]

    def to_mail(self, notifiable: Any) -> Mailable:
        url = ""
        if hasattr(notifiable, "verification_url"):
            url = str(notifiable.verification_url())

        class VerifyMail(Mailable):
            def envelope(self) -> Envelope:
                return Envelope(subject="Verify Email Address")

            def content(self) -> Content:
                return Content(
                    text=f"Please verify your email address: {url}",
                    html=(
                        "<p>Please click the button below to verify your email address.</p>"
                        f'<p><a href="{url}">Verify Email Address</a></p>'
                    ),
                )

        return VerifyMail()

    def to_database(self, notifiable: Any) -> dict[str, Any]:
        return {"action": "verify-email", "email": getattr(notifiable, "email", None)}
