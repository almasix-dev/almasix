"""Demo RateLimiter, throttle middleware, and login throttling (M35)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from starlette.requests import Request as StarletteRequest

from almasix.auth import LoginRateLimiter
from almasix.console.command import Command
from almasix.http import Limit, RateLimiter
from almasix.http.exceptions import TooManyRequestsHttpException
from almasix.http.rate_limiting import parse_rate
from almasix.http.request import Request


class ProgressRateLimitingCommand(Command):
    signature = "progress:rate-limiting"
    description = "Demo RateLimiter, throttle middleware, and login throttling (M35)"

    def handle(self) -> int:
        self._facade()
        self._named_limiter()
        self._throttle_route()
        self._login_throttle()
        self.success("rate-limiting demo ok")
        return 0

    def _facade(self) -> None:
        key = "progress:demo:send"
        RateLimiter.clear(key)
        self.info("RateLimiter façade (cache-backed)")
        ran = RateLimiter.attempt(key, 2, lambda: "sent", decay_seconds=60)
        self.line(f"    attempt #1          -> {ran!r}")
        ran = RateLimiter.attempt(key, 2, lambda: "sent", decay_seconds=60)
        self.line(f"    attempt #2          -> {ran!r}")
        blocked = RateLimiter.attempt(key, 2, lambda: "sent", decay_seconds=60)
        self.line(f"    attempt #3 (over)   -> {blocked!r}")
        self.line(f"    attempts            -> {RateLimiter.attempts(key)}")
        self.line(f"    remaining           -> {RateLimiter.remaining(key, 2)}")
        self.line(f"    available_in        -> {RateLimiter.available_in(key)}s")
        RateLimiter.clear(key)
        self.line("    clear               -> attempts reset")
        max_attempts, decay = parse_rate("60,1")
        self.line(f"    parse_rate('60,1')  -> {max_attempts} / {decay}s")

    def _named_limiter(self) -> None:
        self.info("named limiter")
        registered = RateLimiter.limiter("api") is not None
        self.line(f"    RateLimiter.for_('api') registered  -> {registered}")
        self.line("    attach with middleware=['throttle:api']")
        self.line("    Limit.per_minute / per_hour / per_day / none()")
        self.line("    middleware.throttle_api() puts throttle:api on the api group")

    def _throttle_route(self) -> None:
        # Console commands boot the application without loading HTTP routes.
        # Ensure the `/api/*` endpoints exist before we exercise them.
        self.app.load_routes()
        # Wipe any prior demo hits so the four-request story is deterministic.
        for suffix in ("127.0.0.1", "testclient", "0.0.0.0"):
            RateLimiter.clear(f"progress|progress:{suffix}")

        client = TestClient(self.app.asgi)
        statuses: list[int] = []
        last_headers: dict[str, str] = {}
        for _ in range(4):
            response = client.get("/api/throttle-demo")
            statuses.append(response.status_code)
            if response.status_code == 429:
                last_headers = {
                    "Retry-After": response.headers.get("retry-after", ""),
                    "X-RateLimit-Limit": response.headers.get("x-ratelimit-limit", ""),
                    "X-RateLimit-Remaining": response.headers.get(
                        "x-ratelimit-remaining", ""
                    ),
                }

        self.info("throttle middleware (/api/throttle-demo → throttle:progress)")
        self.line(f"    four hits            -> {statuses}")
        if last_headers:
            self.line(
                f"    429 headers          -> Retry-After={last_headers['Retry-After']} "
                f"Limit={last_headers['X-RateLimit-Limit']} "
                f"Remaining={last_headers['X-RateLimit-Remaining']}"
            )
        if statuses.count(200) != 3 or 429 not in statuses:
            raise RuntimeError(f"expected three 200s then a 429, got {statuses}")

    def _login_throttle(self) -> None:
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/login",
            "raw_path": b"/login",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("test", 80),
        }
        request = Request(StarletteRequest(scope))
        request._input = {"email": "attacker@example.com", "password": "nope"}  # noqa: SLF001

        limiter = LoginRateLimiter(max_attempts=3, decay_seconds=60)
        RateLimiter.clear(limiter.key(request))
        self.info("login throttling")
        for index in range(3):
            limiter.hit(request)
            self.line(f"    failed login #{index + 1}   -> hit")
        if not limiter.too_many_attempts(request):
            raise RuntimeError("login limiter should be exhausted")
        try:
            limiter.raise_for(request)
            raise RuntimeError("raise_for should have raised")
        except TooManyRequestsHttpException as exc:
            self.line(f"    raise_for            -> 429 {exc.message!r}")
            self.line(f"    Retry-After          -> {exc.headers.get('Retry-After')}")
        self.line("    attempt_login(...)   wraps auth().attempt with hit/clear")
        RateLimiter.clear(limiter.key(request))
