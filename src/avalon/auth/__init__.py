"""Authentication guards, middleware (M7), and authorization (M19)."""

from __future__ import annotations

from avalon.auth.access import (
    AccessGate,
    Authorizable,
    AuthorizationException,
    AuthorizationResponse,
    AuthorizesRequests,
    Authorize,
    Gate,
    HandlesAuthorization,
    Policy,
    authorize,
    gate,
)
from avalon.auth.authenticatable import AuthenticatableMixin
from avalon.auth.contracts import Authenticatable, UserProvider
from avalon.auth.events import (
    Attempting,
    Authenticated,
    Failed,
    Login,
    Logout,
    OtherDeviceLogout,
    PasswordReset,
    Validated,
    dispatch,
    forget,
    listen,
)
from avalon.auth.guard import (
    AuthManager,
    Guard,
    SessionGuard,
    TokenGuard,
    auth,
    guest,
    pull_intended_url,
    store_intended_url,
)
from avalon.auth.middleware import (
    Authenticate,
    AuthenticateWithBasicAuth,
    EnsureEmailIsVerified,
    RedirectIfAuthenticated,
    RequirePassword,
    StartAuth,
    mark_password_confirmed,
)
from avalon.auth.passwords import Password
from avalon.auth.providers import ArticulateUserProvider, MemoryUserProvider

__all__ = [
    "AccessGate",
    "ArticulateUserProvider",
    "Authorizable",
    "AuthorizationException",
    "AuthorizationResponse",
    "AuthorizesRequests",
    "Authorize",
    "Attempting",
    "AuthManager",
    "Authenticate",
    "AuthenticateWithBasicAuth",
    "Authenticated",
    "Authenticatable",
    "AuthenticatableMixin",
    "EnsureEmailIsVerified",
    "Failed",
    "Gate",
    "Guard",
    "HandlesAuthorization",
    "Login",
    "Logout",
    "MemoryUserProvider",
    "OtherDeviceLogout",
    "Password",
    "PasswordReset",
    "Policy",
    "RedirectIfAuthenticated",
    "RequirePassword",
    "SessionGuard",
    "StartAuth",
    "TokenGuard",
    "UserProvider",
    "Validated",
    "auth",
    "authorize",
    "dispatch",
    "forget",
    "gate",
    "guest",
    "listen",
    "mark_password_confirmed",
    "pull_intended_url",
    "store_intended_url",
]
