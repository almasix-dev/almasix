"""Rate limiting — how many times a key may be used in a window.

Laravel's `RateLimiter` is a thin counter over the cache: each `hit` /
`increment` bumps the count and the first hit in a window sets the timer.
Named limiters (`RateLimiter.for_("api", ...)`) are what the `throttle`
middleware looks up; `attempt` is the helper for "do this, but not more
than N times a minute".
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from almasix.cache import Cache

LimiterCallback = Callable[[Any], "Limit | Sequence[Limit] | None"]
AfterCallback = Callable[[Any], bool]
ResponseCallback = Callable[..., Any]

#: Named limiters registered by `RateLimiter.for_`.
_limiters: dict[str, LimiterCallback] = {}


@dataclass
class Limit:
    """How many times, how often, and by which key.

    `by` is typically a user id or an IP. Leaving it empty means "everyone
    shares one bucket", which is almost never what you want. Return
    `Limit.none()` from a named limiter to skip throttling for that request.
    """

    max_attempts: int | None
    decay_seconds: int = 60
    key: str = ""
    response_callback: ResponseCallback | None = field(default=None, repr=False)
    after_callback: AfterCallback | None = field(default=None, repr=False)

    @classmethod
    def none(cls) -> Limit:
        """Unlimited — the `throttle` middleware skips this limit entirely."""
        return cls(max_attempts=None)

    @classmethod
    def per_second(cls, max_attempts: int) -> Limit:
        return cls(max_attempts=max_attempts, decay_seconds=1)

    @classmethod
    def per_minute(cls, max_attempts: int) -> Limit:
        return cls(max_attempts=max_attempts, decay_seconds=60)

    @classmethod
    def per_hour(cls, max_attempts: int) -> Limit:
        return cls(max_attempts=max_attempts, decay_seconds=3600)

    @classmethod
    def per_day(cls, max_attempts: int) -> Limit:
        return cls(max_attempts=max_attempts, decay_seconds=86400)

    def by(self, key: Any) -> Limit:
        self.key = str(key)
        return self

    def response(self, callback: ResponseCallback) -> Limit:
        self.response_callback = callback
        return self

    def after(self, callback: AfterCallback) -> Limit:
        """Only count the request when ``callback(response)`` is truthy."""
        self.after_callback = callback
        return self

    @property
    def is_unlimited(self) -> bool:
        return self.max_attempts is None


class RateLimiter:
    """Cache-backed rate limiter (Laravel ``RateLimiter``)."""

    PREFIX = "almasix:rate:"

    @classmethod
    def for_(cls, name: str, callback: LimiterCallback) -> None:
        """Register a named limiter for the `throttle` middleware."""
        _limiters[name] = callback

    # `for` is a keyword in Python; Laravel's spelling is offered as an alias.
    for_name = for_

    @classmethod
    def limiter(cls, name: str) -> LimiterCallback | None:
        return _limiters.get(name)

    @classmethod
    def clear_limiters(cls) -> None:
        """Drop every named limiter — for tests that register their own."""
        _limiters.clear()

    @classmethod
    def attempt(
        cls,
        key: str,
        max_attempts: int,
        callback: Callable[[], Any],
        decay_seconds: int = 60,
    ) -> Any:
        """Run ``callback`` if the key still has attempts left; else `False`."""
        if cls.too_many_attempts(key, max_attempts):
            return False
        result = callback()
        cls.hit(key, decay_seconds)
        return True if result is None else result

    @classmethod
    def too_many_attempts(cls, key: str, max_attempts: int) -> bool:
        if max_attempts is None:  # type: ignore[comparison-overlap]
            return False
        return cls.attempts(key) >= int(max_attempts)

    @classmethod
    def hit(cls, key: str, decay_seconds: int = 60, amount: int = 1) -> int:
        """Increment the counter for ``key`` (Laravel ``hit`` / ``increment``)."""
        return cls.increment(key, decay_seconds=decay_seconds, amount=amount)

    @classmethod
    def increment(cls, key: str, decay_seconds: int = 60, amount: int = 1) -> int:
        """Bump the counter by ``amount`` and plant / keep the window timer."""
        store = cls._store()
        counter = cls._counter_key(key)
        timer = cls._timer_key(key)
        decay = max(1, int(decay_seconds))
        delta = int(amount)
        # First hit in the window plants the timer; later hits keep it.
        store.add(timer, int(time.time()) + decay, decay)
        attempts = store.increment(counter, delta)
        if attempts is False or attempts is None:
            attempts = delta
            store.put(counter, int(attempts), decay)
        remaining = cls.available_in(key) or decay
        store.put(counter, int(attempts), remaining)
        return int(attempts)

    @classmethod
    def attempts(cls, key: str) -> int:
        value = cls._store().get(cls._counter_key(key), 0)
        return int(value or 0)

    @classmethod
    def retries_left(cls, key: str, max_attempts: int) -> int:
        if max_attempts is None:  # type: ignore[comparison-overlap]
            return 0
        return max(0, int(max_attempts) - cls.attempts(key))

    remaining = retries_left

    @classmethod
    def available_in(cls, key: str) -> int:
        """Seconds until the window resets; 0 when the key is clear."""
        ends_at = cls._store().get(cls._timer_key(key))
        if ends_at is None:
            return 0
        return max(0, int(ends_at) - int(time.time()))

    @classmethod
    def clear(cls, key: str) -> None:
        store = cls._store()
        store.forget(cls._counter_key(key))
        store.forget(cls._timer_key(key))

    @classmethod
    def reset_attempts(cls, key: str) -> None:
        cls._store().forget(cls._counter_key(key))

    @classmethod
    def _store(cls) -> Any:
        """Use ``cache.limiter`` when configured; otherwise the default store."""
        name: str | None = None
        try:
            from almasix.config import config

            raw = config("cache.limiter")
            if raw:
                name = str(raw)
        except Exception:
            name = None
        if name:
            return Cache.store(name)
        return Cache

    @classmethod
    def _counter_key(cls, key: str) -> str:
        return f"{cls.PREFIX}{key}:attempts"

    @classmethod
    def _timer_key(cls, key: str) -> str:
        return f"{cls.PREFIX}{key}:timer"


# Laravel spells the registrar `for`; Python needs `for_` / `for_name`.
setattr(RateLimiter, "for", RateLimiter.for_)
RateLimiter.tooManyAttempts = RateLimiter.too_many_attempts  # type: ignore[attr-defined]
RateLimiter.retriesLeft = RateLimiter.retries_left  # type: ignore[attr-defined]
RateLimiter.availableIn = RateLimiter.available_in  # type: ignore[attr-defined]
RateLimiter.resetAttempts = RateLimiter.reset_attempts  # type: ignore[attr-defined]


def parse_rate(rate: str) -> tuple[int, int]:
    """`60,1` → (60 attempts, 60 seconds). The second number is minutes.

    A bare `60` means 60 attempts per minute. `60|10` is the authenticated /
    guest form Laravel accepts on `throttle:60|10`.
    """
    text = str(rate).strip()
    if "|" in text:
        # Caller picks the half; we only parse one side at a time.
        text = text.split("|", 1)[0].strip()
    parts = [part.strip() for part in text.split(",")]
    max_attempts = int(parts[0] or 60)
    decay_minutes = float(parts[1]) if len(parts) > 1 and parts[1] else 1.0
    return max_attempts, max(1, int(math.ceil(decay_minutes * 60)))
