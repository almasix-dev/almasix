"""Email verification — ``MustVerifyEmail`` mixin + signed URLs."""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode


class MustVerifyEmail:
    """Laravel-shaped email verification helpers for Authenticatable models."""

    def has_verified_email(self) -> bool:
        value = getattr(self, "email_verified_at", None)
        if value is None and hasattr(self, "get_attribute"):
            value = self.get_attribute("email_verified_at")  # type: ignore[misc]
        return value is not None

    async def mark_email_as_verified(self) -> bool:
        now = datetime.now(UTC)
        if hasattr(self, "set_attribute"):
            self.set_attribute("email_verified_at", now)  # type: ignore[misc]
        else:
            self.email_verified_at = now
        if hasattr(self, "save"):
            result = self.save()
            if hasattr(result, "__await__"):
                await result  # type: ignore[misc]
        return True

    def verification_url(self, *, base_url: str | None = None, expires: int = 60) -> str:
        """Signed verification URL (HMAC with ``APP_KEY``).

        Shape: ``{base}/email/verify/{id}/{hash}?expires=…&signature=…``
        ``expires`` is minutes from now (Laravel default 60).
        """
        email = str(getattr(self, "email", "") or "")
        key = getattr(self, "get_key", lambda: getattr(self, "id", ""))()
        email_hash = hash_email(email)
        expires_at = int(time.time()) + int(expires) * 60
        signature = sign_verification(str(key), email_hash, expires_at)
        root = (base_url if base_url is not None else _app_url()).rstrip("/")
        query = urlencode({"expires": expires_at, "signature": signature})
        return f"{root}/email/verify/{key}/{email_hash}?{query}"

    async def send_email_verification_notification(self) -> Any:
        from almasix.notifications.messages import VerifyEmailNotification

        notify = getattr(self, "notify", None)
        if callable(notify):
            return await notify(VerifyEmailNotification())
        from almasix.notifications.helpers import notify as send

        return await send(self, VerifyEmailNotification())


def hash_email(email: str) -> str:
    return hashlib.sha256(email.encode("utf-8")).hexdigest()


def sign_verification(user_id: str, email_hash: str, expires_at: int) -> str:
    payload = f"{user_id}|{email_hash}|{expires_at}"
    return hmac.new(_app_key_bytes(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_signature(
    user_id: str,
    email_hash: str,
    expires_at: int | str,
    signature: str,
) -> bool:
    try:
        expires_int = int(expires_at)
    except (TypeError, ValueError):
        return False
    if expires_int < int(time.time()):
        return False
    expected = sign_verification(str(user_id), email_hash, expires_int)
    return hmac.compare_digest(expected, str(signature or ""))


async def mark_verified_from_request(
    *,
    user_id: str,
    email_hash: str,
    expires: str | int,
    signature: str,
    user_model: type | None = None,
) -> Any | None:
    """Validate a signed URL and mark the user verified. Returns the user or None."""
    if not verify_signature(user_id, email_hash, expires, signature):
        return None
    model = user_model or _default_user_model()
    if model is None:
        return None
    finder = getattr(model, "find", None)
    if not callable(finder):
        return None
    user = finder(user_id)
    if hasattr(user, "__await__"):
        user = await user  # type: ignore[misc]
    if user is None:
        return None
    email = str(getattr(user, "email", "") or "")
    if not hmac.compare_digest(hash_email(email), email_hash):
        return None
    if not user.has_verified_email():
        await user.mark_email_as_verified()
    return user


def _app_url() -> str:
    try:
        from almasix.config import config

        return str(config("app.url") or "")
    except Exception:
        return ""


def _app_key_bytes() -> bytes:
    try:
        from almasix.config import config

        key = str(config("app.key") or "almasix-dev-key")
    except Exception:
        key = "almasix-dev-key"
    if key.startswith("base64:"):
        key = key[7:]
    return key.encode("utf-8")


def _default_user_model() -> type | None:
    try:
        from app.models.user import User  # type: ignore

        return User
    except Exception:
        return None
