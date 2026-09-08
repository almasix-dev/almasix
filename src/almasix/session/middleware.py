"""Start the session for the ``web`` middleware group."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.responses import Response as StarletteResponse

from almasix.http.middleware import Middleware, NextCall
from almasix.session.handlers import resolve_session_handler
from almasix.session.store import Session, reset_session, set_session

if TYPE_CHECKING:
    from almasix.http.request import Request


class StartSession(Middleware):
    """Load session state, expose ``request.session``, persist on the way out."""

    cookie_name = "almasix_session"

    async def handle(self, request: Request, call_next: NextCall) -> StarletteResponse:
        from almasix.config import config

        key = str(config("app.key", "") or "")
        if not key:
            key = "almasix-insecure-dev-key-change-me"
        lifetime = int(config("session.lifetime", 120) or 120) * 60
        cookie_name = str(config("session.cookie", self.cookie_name) or self.cookie_name)
        path = str(config("session.path", "/") or "/")
        secure = bool(config("session.secure", False))

        handler = resolve_session_handler()
        session_id, data = await handler.read(
            request, key=key, cookie_name=cookie_name, lifetime=lifetime
        )
        session = Session(data)
        if data is not None:
            session.age_flash()
        request._session = session  # noqa: SLF001
        request._session_id = session_id  # noqa: SLF001
        token = set_session(session)
        try:
            response = await call_next(request)
        finally:
            reset_session(token)

        await handler.write(
            response,
            session_id=session_id,
            data=session.all(),
            key=key,
            cookie_name=cookie_name,
            lifetime=lifetime,
            path=path,
            secure=secure,
            dirty=session.dirty,
            had_prior=data is not None,
        )
        return response
