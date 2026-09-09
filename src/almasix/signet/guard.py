"""Signet authentication guard — SPA session first, then personal access token."""

from __future__ import annotations

from typing import Any

import almasix.auth.events as auth_events
from almasix.auth.guard import Guard, SessionGuard
from almasix.signet.signet import Signet, is_from_frontend
from almasix.signet.transient_token import TransientToken


class SignetGuard(Guard):
    """Laravel ``auth:signet`` — cookie session for first-party SPAs, else Bearer PAT."""

    def __init__(
        self,
        name: str = "signet",
        provider: Any | None = None,
        *,
        manager: Any | None = None,
    ) -> None:
        super().__init__(name, provider)
        self._manager = manager
        self._request: Any | None = None

    def set_request(self, request: Any) -> None:
        self._request = request

    async def hydrate(
        self, request: Any, *, session_guard: SessionGuard | None = None
    ) -> Any | None:
        """Resolve the user for this request into ``self._user``."""
        self._request = request

        acting_user, acting_guard = Signet.take_acting_as()
        if acting_user is not None and (acting_guard in (None, self.name, "signet")):
            self.once(acting_user)
            return acting_user

        # 1) First-party SPA: reuse the web session user.
        if session_guard is not None and session_guard.check():
            if is_from_frontend(request) or _has_session_cookie(request):
                user = session_guard.user()
                if user is not None and hasattr(user, "with_access_token"):
                    # SPA: tokenCan always true (TransientToken with *).
                    if user.current_access_token() is None:
                        user.with_access_token(TransientToken(["*"]))
                self.once(user)
                return user

        # 2) Bearer personal access token.
        bearer = getattr(request, "bearer_token", lambda: None)()
        if not bearer:  # pragma: no cover
            return None
        return await self.set_user_from_request_token(str(bearer))  # pragma: no branch

    async def set_user_from_request_token(self, token: str | None) -> Any | None:
        if not token:  # pragma: no cover
            return None
        model_cls = Signet.personal_access_token_model()
        try:
            access = await model_cls.find_token(token)
        except Exception:  # pragma: no cover - DB / schema soft-fail
            return None
        if access is None or access.is_expired():
            return None

        tokenable = await _resolve_tokenable(access)
        if tokenable is None:  # pragma: no cover
            return None
        if hasattr(tokenable, "with_access_token"):
            tokenable.with_access_token(access)
        try:
            await access.touch_last_used()
        except Exception:  # pragma: no cover - best-effort stamp
            pass
        self.once(tokenable)
        await auth_events.dispatch(auth_events.Authenticated(user=tokenable, guard=self.name))
        return tokenable

    async def attempt(
        self,
        credentials: dict[str, Any],
        *,
        remember: bool = False,
    ) -> bool:
        token = credentials.get("token") or credentials.get("api_token")
        if not token:
            return False
        user = await self.set_user_from_request_token(str(token))
        return user is not None

    async def validate(self, credentials: dict[str, Any]) -> bool:
        return await self.attempt(credentials)


def _has_session_cookie(request: Any) -> bool:
    try:
        cookies = request.cookies
    except Exception:
        return False
    if not cookies:  # pragma: no cover
        return False
    # Any session cookie suggests a browser client that already established state.
    for name in cookies:
        if "session" in str(name).lower():
            return True
    return False


async def _resolve_tokenable(access: Any) -> Any | None:
    """Load the owning model from morph columns."""
    type_name = access.get_raw_attribute("tokenable_type") or access.get_attribute("tokenable_type")
    tokenable_id = access.get_raw_attribute("tokenable_id") or access.get_attribute("tokenable_id")
    if not type_name or tokenable_id is None:  # pragma: no cover
        return None

    from almasix.auth.guard import _import_string
    from almasix.orm.morph import morph_target

    model_cls = morph_target(str(type_name))
    if model_cls is None and "." in str(type_name):
        try:
            model_cls = _import_string(str(type_name))
        except Exception:  # pragma: no cover
            model_cls = None
    if model_cls is None:
        try:
            from almasix.config import config

            model_path = config("auth.providers.users.model")
            if model_path:
                candidate = _import_string(str(model_path))
                if candidate.__name__ == str(type_name):
                    model_cls = candidate
        except Exception:  # pragma: no cover
            model_cls = None

    if model_cls is None:
        return None
    try:
        return await model_cls.query().find(tokenable_id)
    except Exception:  # pragma: no cover
        return None
