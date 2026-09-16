"""Application entry — boots the Almasix kernel and exposes ASGI."""

from __future__ import annotations

from pathlib import Path

from almasix.framework import Application, Middleware
from almasix.translation import SetLocaleMiddleware

BASE_PATH = Path(__file__).resolve().parent.parent


def configure_middleware(middleware: Middleware) -> None:
    """Register HTTP middleware (Laravel ``bootstrap/app.php`` shape)."""
    from almasix.auth import (
        Authenticate,
        AuthenticateWithBasicAuth,
        Authorize,
        EnsureEmailIsVerified,
        RedirectIfAuthenticated,
        RequirePassword,
    )
    from almasix.auth.middleware import StartAuth
    from almasix.session import EncryptCookies, StartSession, VerifyCsrfToken
    from almasix.signet import CheckAbilities, CheckForAnyAbility

    middleware.alias(
        {
            "locale": SetLocaleMiddleware,
            "cookies.encrypt": EncryptCookies,
            "session.start": StartSession,
            "csrf": VerifyCsrfToken,
            "auth.start": StartAuth,
            "auth": Authenticate,
            "guest": RedirectIfAuthenticated,
            "password.confirm": RequirePassword,
            "auth.basic": AuthenticateWithBasicAuth,
            "verified": EnsureEmailIsVerified,
            "can": Authorize,
            "abilities": CheckAbilities,
            "ability": CheckForAnyAbility,
            "inertia": "inertia.middleware.HandleInertiaRequests",
        }
    )
    middleware.web(
        prepend=["cookies.encrypt", "session.start", "csrf", "auth.start"],
        append=["locale", "inertia"],
    )
    middleware.api(prepend=["auth.start"], append=["locale"])
    middleware.stateful_api()


application = (
    Application.configure(BASE_PATH)
    .with_middleware(configure_middleware)
    .create()
)
asgi = application.asgi
