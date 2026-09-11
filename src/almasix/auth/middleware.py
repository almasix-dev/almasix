"""``auth`` / ``guest`` / password.confirm / HTTP Basic middleware."""

from __future__ import annotations

import base64
import time
from typing import TYPE_CHECKING, Any

from starlette.responses import Response as StarletteResponse

from almasix.auth.cookies import apply_queued_cookies, begin_cookie_queue, reset_cookie_queue
from almasix.auth.guard import (
    AuthManager,
    SessionGuard,
    TokenGuard,
    get_auth,
    reset_auth,
    set_auth,
    store_intended_url,
)
from almasix.http.exceptions import UnauthorizedHttpException
from almasix.http.middleware import Middleware, NextCall
from almasix.http.response import redirect
from almasix.translation import __

if TYPE_CHECKING:
    from almasix.http.request import Request

_PASSWORD_CONFIRMED_AT = "auth.password_confirmed_at"


class StartAuth(Middleware):
    """Hydrate guards from session / remember cookie / bearer token / viaRequest."""

    async def handle(self, request: Request, call_next: NextCall) -> StarletteResponse:
        manager = AuthManager()
        manager.configure_from_config()
        cookie_token = begin_cookie_queue()

        try:
            session = request.session
        except RuntimeError:
            session = None

        for name in _configured_guard_names():
            guard = manager.guard(name)
            if isinstance(guard, SessionGuard) and session is not None:
                payload = session.get(f"login_{guard.name}")
                if payload is not None:
                    # Bind loop vars into defaults so the lambda cannot see a later iteration.
                    user = await _safe_resolve(lambda g=guard, p=payload: _hydrate_user(g, p))
                    if user is not None:
                        guard.once(user)
                else:
                    remembered = await _safe_resolve(
                        lambda g=guard: _from_remember_cookie(request, g)
                    )
                    if remembered is not None:
                        guard.once(remembered)
                        guard._via_remember = True
                        session.put(f"login_{guard.name}", {"id": guard.id()})
            if isinstance(guard, TokenGuard):
                bearer = request.bearer_token()
                query_token = request.query(guard.input_key)
                token = bearer or (str(query_token) if query_token else None)
                if token:
                    # Soft-fail: missing schema / provider errors must not 500 public routes
                    # that happen to send Authorization (M2 demo Bearer on /api/items/…).
                    await _safe_resolve(lambda g=guard, t=token: g.set_user_from_request_token(t))
            from almasix.signet.guard import SignetGuard

            if isinstance(guard, SignetGuard):
                session_guard = None
                try:
                    candidate = manager.guard("web")
                    if isinstance(candidate, SessionGuard):
                        session_guard = candidate
                except Exception:
                    session_guard = None
                await _safe_resolve(
                    lambda g=guard, r=request, s=session_guard: g.hydrate(r, session_guard=s)
                )
            if guard._via_request is not None and guard.guest():
                try:
                    resolved = guard._via_request(request)
                    if hasattr(resolved, "__await__"):
                        resolved = await resolved  # type: ignore[misc]
                    if resolved is not None:  # pragma: no branch
                        guard.once(resolved)
                except Exception:
                    pass

        request._auth = manager
        token = set_auth(manager)
        try:
            response = await call_next(request)
            apply_queued_cookies(response)
            return response
        finally:
            reset_auth(token)
            reset_cookie_queue(cookie_token)


class Authenticate(Middleware):
    """Require an authenticated user (alias: ``auth``, optional ``auth:guard``)."""

    def __init__(self, guard=None) -> None:
        self.guard_name = guard

    async def handle(self, request: Request, call_next: NextCall) -> StarletteResponse:
        manager = get_auth() or getattr(request, "_auth", None)
        if manager is None:
            return await _unauthenticated(request)
        target = manager.guard(self.guard_name) if self.guard_name else manager.guard()
        ok = target.check() if self.guard_name else manager.check()
        if not ok:
            return await _unauthenticated(request)
        return await call_next(request)


class EnsureEmailIsVerified(Middleware):
    """Require a verified email (alias: ``verified``) — Laravel-shaped."""

    async def handle(self, request: Request, call_next: NextCall) -> StarletteResponse:
        manager = get_auth() or getattr(request, "_auth", None)
        user = manager.user() if manager is not None else None
        if user is None:
            return await _unauthenticated(request)
        checker = getattr(user, "has_verified_email", None)
        if callable(checker) and not checker():
            from almasix.http.exceptions import ForbiddenHttpException

            if _wants_json(request):
                raise ForbiddenHttpException("Your email address is not verified.")
            return redirect("/email/verify")
        return await call_next(request)


class RedirectIfAuthenticated(Middleware):
    """Send authenticated users away from guest-only pages (alias: ``guest``)."""

    def __init__(self, guard=None) -> None:
        self.guard_name = guard

    async def handle(self, request: Request, call_next: NextCall) -> StarletteResponse:
        manager = get_auth() or getattr(request, "_auth", None)
        if manager is not None:
            if self.guard_name:
                if manager.guard(self.guard_name).check():
                    return redirect("/")
            elif manager.check():
                return redirect("/")
        return await call_next(request)


class RequirePassword(Middleware):
    """Confirm password recently (alias: ``password.confirm``)."""

    def __init__(self, timeout=None) -> None:
        self.timeout = timeout

    async def handle(self, request: Request, call_next: NextCall) -> StarletteResponse:
        try:
            from almasix.config import config

            timeout = self.timeout
            if timeout is None:
                timeout = int(config("auth.password_timeout", 10800) or 10800)
        except Exception:
            timeout = self.timeout or 10800

        try:
            session = request.session
        except RuntimeError:
            if _wants_json(request):
                raise UnauthorizedHttpException(__("auth.password")) from None
            return _redirect_to_password_confirm(request)

        confirmed_at = session.get(_PASSWORD_CONFIRMED_AT)
        if confirmed_at is None or (time.time() - float(confirmed_at)) > timeout:
            if _wants_json(request):
                raise UnauthorizedHttpException(__("auth.password"))
            return _redirect_to_password_confirm(request)
        return await call_next(request)


def _password_confirm_path() -> str:
    """Prefer the named ``password.confirm`` route; fall back to ``/confirm-password``."""
    try:
        from almasix.routing.router import get_router

        named = get_router().route_named("password.confirm")
        if named is not None:
            uri = str(named.uri or "").strip()
            if uri:
                return uri if uri.startswith("/") else f"/{uri}"
    except Exception:
        pass
    return "/confirm-password"


def _redirect_to_password_confirm(request: Request) -> StarletteResponse:
    store_intended_url(_intended_url_for_password_confirm(request))
    return redirect(_password_confirm_path())


def _intended_url_for_password_confirm(request: Request) -> str:
    """URL to resume after confirming — must be a safe GET target.

    Mutating requests (DELETE/POST/…) cannot be replayed by a redirect, and
    paths like ``DELETE /user`` often have no GET twin (404 after confirm).
    Prefer Referer, then the request path only for GET/HEAD.
    """
    method = (getattr(request, "method", None) or "GET").upper()
    if method in {"GET", "HEAD"}:
        intended = request.path or "/"
        query = getattr(getattr(request, "raw", None), "url", None)
        raw_query = getattr(query, "query", None) if query is not None else None
        if not raw_query:
            try:
                raw_query = request.raw.url.query  # type: ignore[attr-defined]
            except Exception:
                raw_query = ""
        if raw_query:
            intended = f"{intended}?{raw_query}"
        return intended

    referer = (request.header("Referer") or request.header("referer") or "").strip()
    if referer:
        from urllib.parse import urlparse

        parsed = urlparse(referer)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return path
    return "/dashboard"


class AuthenticateWithBasicAuth(Middleware):
    """HTTP Basic authentication (Laravel ``auth.basic``)."""

    def __init__(self, field="email", realm="Login") -> None:
        self.field = field
        self.realm = realm

    async def handle(self, request: Request, call_next: NextCall) -> StarletteResponse:
        manager = get_auth() or getattr(request, "_auth", None) or AuthManager()
        header = request.header("Authorization") or ""
        if header.lower().startswith("basic "):
            try:
                decoded = base64.b64decode(header[6:].strip()).decode("utf-8")
                username, _, password = decoded.partition(":")
            except Exception:
                username = password = ""
            if username and await manager.attempt({self.field: username, "password": password}):
                return await call_next(request)

        response = StarletteResponse(status_code=401, content=b"Unauthorized")
        response.headers["WWW-Authenticate"] = f'Basic realm="{self.realm}"'
        return response


def mark_password_confirmed(request: Request) -> None:
    request.session.put(_PASSWORD_CONFIRMED_AT, time.time())


async def _unauthenticated(request: Request) -> StarletteResponse:
    if _wants_json(request):
        raise UnauthorizedHttpException("Unauthenticated.")
    intended = request.path
    query = request.raw.url.query
    if query:
        intended = f"{request.path}?{query}"
    store_intended_url(intended)
    return redirect("/login")


async def _safe_resolve(factory) -> Any | None:
    """Run an auth lookup; treat provider/DB failures as unauthenticated."""
    try:
        return await factory()
    except Exception:
        return None


async def _hydrate_user(guard: SessionGuard, payload: Any) -> Any | None:
    if guard.provider is None:
        return payload
    identifier = payload.get("id") if isinstance(payload, dict) else payload
    if identifier is None:  # pragma: no branch
        return payload
    user = await guard.provider.retrieve_by_id(identifier)
    return user if user is not None else payload


async def _from_remember_cookie(request: Request, guard: SessionGuard) -> Any | None:
    if guard.provider is None:
        return None
    raw = request.cookie(guard.remember_cookie_name())
    if not raw or "|" not in str(raw):
        return None
    identifier, _, token = str(raw).partition("|")
    if not identifier or not token:
        return None
    return await guard.provider.retrieve_by_token(identifier, token)


def _configured_guard_names() -> list[str]:
    names = ["web", "api"]
    try:
        from almasix.config import config

        configured = list((config("auth.guards", {}) or {}).keys())
        if configured:
            # Preserve web/api first for DX, then any custom guards.
            ordered = []
            for name in names + configured:
                if name not in ordered:
                    ordered.append(name)
            return ordered
    except Exception:
        pass
    return names


def _wants_json(request: Request) -> bool:
    accept = (request.header("Accept") or "").lower()
    return request.is_json() or "application/json" in accept or request.path.startswith("/api")
