"""Throttle middleware — refuse a request that has used its budget.

`throttle:60,1` means 60 attempts per minute. `throttle:api` looks up the
named limiter registered with `RateLimiter.for_("api", ...)`. `throttle:60|10`
uses 60 for guests and 10 for authenticated users. The response carries
`X-RateLimit-Limit`, `X-RateLimit-Remaining`, and on a refusal `Retry-After`
plus `X-RateLimit-Reset`.
"""

from __future__ import annotations

import inspect
import time
from typing import Any

from almasix.http.exceptions import TooManyRequestsHttpException
from almasix.http.middleware import Middleware
from almasix.http.rate_limiting import Limit, RateLimiter, parse_rate
from almasix.http.request import Request


class ThrottleRequests(Middleware):
    """Laravel's `throttle` middleware."""

    def __init__(self, limiter: str | None = None) -> None:
        # `throttle:api` or `throttle:60,1`. Empty means 60/minute by IP.
        self.limiter = str(limiter or "60,1").strip()

    async def handle(self, request: Request, call_next: Any) -> Any:
        limits = self._limits_for(request)
        active = [limit for limit in limits if not limit.is_unlimited]
        # Check every limit before hitting any, so a request that fails the
        # second limit does not consume a slot on the first.
        for limit in active:
            key = self._key(request, limit)
            assert limit.max_attempts is not None
            if RateLimiter.too_many_attempts(key, limit.max_attempts):
                return self._build_refusal(request, limit, key)

        response = await call_next(request)
        for limit in active:
            key = self._key(request, limit)
            if limit.after_callback is not None and not limit.after_callback(response):
                self._attach_headers(response, limit, key)
                continue
            RateLimiter.hit(key, limit.decay_seconds)
            self._attach_headers(response, limit, key)
        return response

    def _limits_for(self, request: Request) -> list[Limit]:
        named = RateLimiter.limiter(self.limiter)
        if named is not None:
            result = named(request)
            if result is None:
                return []
            if isinstance(result, Limit):
                return [result]
            return list(result)

        rate = self._resolve_rate_string(request)
        max_attempts, decay = parse_rate(rate)
        return [
            Limit(max_attempts=max_attempts, decay_seconds=decay).by(self._default_key(request))
        ]

    def _resolve_rate_string(self, request: Request) -> str:
        """`60|10` → guest half or authenticated half."""
        if "|" not in self.limiter:
            return self.limiter
        guest, _, auth = self.limiter.partition("|")
        return auth.strip() if self._user(request) is not None else guest.strip()

    def _key(self, request: Request, limit: Limit) -> str:
        suffix = limit.key or self._default_key(request)
        return f"{self.limiter}|{suffix}"

    def _default_key(self, request: Request) -> str:
        user = self._user(request)
        if user is not None and getattr(user, "id", None) is not None:
            return f"user:{user.id}"
        return f"ip:{request.ip() or _ip(request)}"

    def _user(self, request: Request) -> Any:
        user = getattr(request, "user", None)
        if callable(user):
            user = user()
        return user

    def _attach_headers(self, response: Any, limit: Limit, key: str) -> None:
        headers = getattr(response, "headers", None)
        if headers is None or limit.max_attempts is None:
            return
        remaining = RateLimiter.retries_left(key, limit.max_attempts)
        headers["X-RateLimit-Limit"] = str(limit.max_attempts)
        headers["X-RateLimit-Remaining"] = str(remaining)

    def _build_refusal(self, request: Request, limit: Limit, key: str) -> Any:
        retry = RateLimiter.available_in(key)
        headers = {
            "Retry-After": str(retry),
            "X-RateLimit-Limit": str(limit.max_attempts or 0),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(time.time()) + retry),
        }
        if limit.response_callback is not None:
            return self._invoke_response(limit.response_callback, request, headers)

        raise TooManyRequestsHttpException(
            "Too Many Attempts.",
            headers=headers,
        )

    def _invoke_response(
        self,
        callback: Any,
        request: Request,
        headers: dict[str, str],
    ) -> Any:
        try:
            signature = inspect.signature(callback)
            params = list(signature.parameters.values())
        except (TypeError, ValueError):
            params = []
        if len(params) >= 2:
            return callback(request, headers)
        if len(params) == 1:
            return callback(request)
        return callback()


def _ip(request: Request) -> str:
    forwarded = request.header("x-forwarded-for")
    if forwarded:
        return str(forwarded).split(",")[0].strip()
    client = getattr(getattr(request, "raw", None), "client", None)
    if client is not None and getattr(client, "host", None):
        return str(client.host)
    return "127.0.0.1"
