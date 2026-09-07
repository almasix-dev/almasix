"""Application entry — boots the Avalon kernel and exposes ASGI."""

from __future__ import annotations

from pathlib import Path

from app.http.middleware.demo_tag_middleware import DemoTagMiddleware

from avalon.auth import (
    Authenticate,
    AuthenticateWithBasicAuth,
    Authorize,
    EnsureEmailIsVerified,
    RedirectIfAuthenticated,
    RequirePassword,
)
from avalon.auth.middleware import StartAuth
from avalon.framework import Application, Middleware
from avalon.session import EncryptCookies, StartSession, VerifyCsrfToken
from avalon.translation import SetLocaleMiddleware

BASE_PATH = Path(__file__).resolve().parent.parent


def configure_middleware(middleware: Middleware) -> None:
    """Register HTTP middleware (Laravel ``bootstrap/app.php`` shape)."""
    # Behind a load balancer / ingress (from avalon.http import HEADER_X_FORWARDED_ALL):
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
        }
    )
    middleware.web(
        prepend=["cookies.encrypt", "session.start", "csrf", "auth.start"],
        append=["locale"],
    )
    middleware.api(prepend=["auth.start"], append=["locale", "demo.tag"])


application = (
    Application.configure(BASE_PATH)
    .with_middleware(configure_middleware)
    .create()
)
asgi = application.asgi
