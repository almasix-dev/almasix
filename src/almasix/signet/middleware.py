"""Signet middleware — abilities checks and SPA stateful API stack."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.responses import Response as StarletteResponse

from almasix.auth.guard import get_auth
from almasix.http.exceptions import ForbiddenHttpException, UnauthorizedHttpException
from almasix.http.middleware import Middleware, NextCall
from almasix.signet.signet import is_from_frontend
from almasix.translation import __

if TYPE_CHECKING:
    from almasix.http.request import Request


class CheckAbilities(Middleware):
    """Require the current token to have *all* listed abilities (``abilities:a,b``)."""

    def __init__(self, *abilities: str) -> None:
        self.abilities = _split_abilities(abilities)

    async def handle(self, request: Request, call_next: NextCall) -> StarletteResponse:
        user = _current_user()
        if user is None:
            raise UnauthorizedHttpException(__("auth.unauthenticated") or "Unauthenticated.")
        for ability in self.abilities:
            if not getattr(user, "token_can", lambda _a: False)(ability):
                raise ForbiddenHttpException(__("auth.forbidden") or "Forbidden.")
        return await call_next(request)


class CheckForAnyAbility(Middleware):
    """Require the current token to have *at least one* ability (``ability:a,b``)."""

    def __init__(self, *abilities: str) -> None:
        self.abilities = _split_abilities(abilities)

    async def handle(self, request: Request, call_next: NextCall) -> StarletteResponse:
        user = _current_user()
        if user is None:  # pragma: no cover - auth middleware usually runs first
            raise UnauthorizedHttpException(__("auth.unauthenticated") or "Unauthenticated.")
        token_can = getattr(user, "token_can", None)
        if token_can is None:
            raise ForbiddenHttpException(__("auth.forbidden") or "Forbidden.")
        if not any(token_can(ability) for ability in self.abilities):
            raise ForbiddenHttpException(__("auth.forbidden") or "Forbidden.")
        return await call_next(request)


class EnsureFrontendRequestsAreStateful(Middleware):
    """Mark first-party SPA requests so session + CSRF apply on the API stack.

    Apps that call ``stateful_api()`` in bootstrap should put this middleware
    (or the alias ``signet.stateful``) early on the ``api`` group. Cookie
    session hydration still happens in ``StartAuth``; this middleware is the
    signal that CORS/credentials and CSRF matter for the request.
    """

    async def handle(self, request: Request, call_next: NextCall) -> StarletteResponse:
        if is_from_frontend(request):
            request.state.signet_stateful = True
        return await call_next(request)


def _current_user():
    manager = get_auth()
    if manager is None:  # pragma: no cover
        return None
    return manager.guard("signet").user() or manager.user()


def _split_abilities(abilities: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for item in abilities:
        for part in str(item).split(","):
            part = part.strip()
            if part:
                found.append(part)
    return found
