"""Application entry — boots the Almasix kernel and exposes ASGI."""

from __future__ import annotations

from pathlib import Path

from app.http.middleware.demo_tag_middleware import DemoTagMiddleware

from almasix.auth import (
    Authenticate,
    AuthenticateWithBasicAuth,
    Authorize,
    EnsureEmailIsVerified,
    RedirectIfAuthenticated,
    RequirePassword,
)
from almasix.auth.middleware import StartAuth
from almasix.framework import Application, Middleware
from almasix.signet import CheckAbilities, CheckForAnyAbility
from almasix.session import EncryptCookies, StartSession, VerifyCsrfToken
from almasix.translation import SetLocaleMiddleware

BASE_PATH = Path(__file__).resolve().parent.parent


def configure_middleware(middleware: Middleware) -> None:
    """Register HTTP middleware (Laravel ``bootstrap/app.php`` shape)."""
    # Behind a load balancer / ingress (from almasix.http import HEADER_X_FORWARDED_ALL):
    # middleware.trust_proxies(at="*", headers=HEADER_X_FORWARDED_ALL)
    # middleware.trust_hosts(at=["example.com", "*.example.com"])
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
            "demo.tag": DemoTagMiddleware,
            "abilities": CheckAbilities,
            "ability": CheckForAnyAbility,
        }
    )
    middleware.web(
        prepend=["cookies.encrypt", "session.start", "csrf", "auth.start"],
        append=["locale"],
    )
    middleware.api(prepend=["auth.start"], append=["locale", "demo.tag"])
    # Rate limiting is opt-in per route / via middleware.throttle_api() (M35).
    # The named `api` and `progress` limiters are registered in AppServiceProvider.


application = (
    Application.configure(BASE_PATH)
    .with_middleware(configure_middleware)
    .create()
)
asgi = application.asgi
