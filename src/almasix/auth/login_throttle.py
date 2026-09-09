"""Login rate limiting — lock out a username + IP after too many failures.

Laravel wires this into the login FormRequest. Almasix exposes the same
helpers so a controller (or FormRequest) can say:

    limiter = LoginRateLimiter()
    if limiter.too_many_attempts(request):
        limiter.raise_for(request)
    if not await auth().attempt(...):
        limiter.hit(request)
        ...
    limiter.clear(request)
"""

from __future__ import annotations

from typing import Any

from almasix.http.exceptions import TooManyRequestsHttpException
from almasix.http.rate_limiting import RateLimiter
from almasix.http.request import Request
from almasix.translation import __


class LoginRateLimiter:
    """Throttle failed logins by username + IP (Laravel ``LoginRequest``)."""

    def __init__(self, *, max_attempts: int = 5, decay_seconds: int = 60) -> None:
        self.max_attempts = max_attempts
        self.decay_seconds = decay_seconds

    def key(self, request: Request, username: str | None = None) -> str:
        name = (
            username
            if username is not None
            else str(
                request.input("email") or request.input("username") or request.input("login") or ""
            )
        )
        return f"login|{name.lower()}|{request.ip() or '0.0.0.0'}"

    def too_many_attempts(self, request: Request, username: str | None = None) -> bool:
        return RateLimiter.too_many_attempts(self.key(request, username), self.max_attempts)

    def hit(self, request: Request, username: str | None = None) -> int:
        return RateLimiter.hit(self.key(request, username), self.decay_seconds)

    def clear(self, request: Request, username: str | None = None) -> None:
        RateLimiter.clear(self.key(request, username))

    def available_in(self, request: Request, username: str | None = None) -> int:
        return RateLimiter.available_in(self.key(request, username))

    def raise_for(self, request: Request, username: str | None = None) -> None:
        seconds = self.available_in(request, username)
        message = __(
            "auth.throttle",
            {"seconds": seconds, "minutes": max(1, seconds // 60 or 1)},
        )
        raise TooManyRequestsHttpException(
            message,
            headers={"Retry-After": str(seconds)},
        )


async def attempt_login(
    credentials: dict[str, Any],
    *,
    request: Request,
    remember: bool = False,
    guard: str | None = None,
    limiter: LoginRateLimiter | None = None,
) -> bool:
    """`auth().attempt` with login throttling applied.

    Returns `True` on success (and clears the limiter). On failure hits the
    limiter and returns `False`. Raises `TooManyRequestsHttpException` when
    the budget is already spent.
    """
    from almasix.auth import auth

    rate = limiter or LoginRateLimiter()
    username = str(
        credentials.get("email") or credentials.get("username") or credentials.get("login") or ""
    )
    if rate.too_many_attempts(request, username):
        rate.raise_for(request, username)

    ok = await auth().guard(guard).attempt(credentials, remember=remember)
    if ok:
        rate.clear(request, username)
        return True
    rate.hit(request, username)
    return False
