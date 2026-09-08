"""Authentication guards, middleware (M7), and authorization (M19)."""

from __future__ import annotations

from almasix.auth.access import (
    AccessGate,
    Authorizable,
    AuthorizationException,
    AuthorizationResponse,
    Authorize,
    AuthorizesRequests,
    Gate,
    HandlesAuthorization,
    Policy,
    authorize,
    gate,
)
from almasix.auth.authenticatable import AuthenticatableMixin
from almasix.auth.contracts import Authenticatable, UserProvider
from almasix.auth.events import (
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
from almasix.auth.guard import (
    AuthManager,
    Guard,
    SessionGuard,
    TokenGuard,
    auth,
    guest,
    pull_intended_url,
    store_intended_url,
)
from almasix.auth.middleware import (
    Authenticate,
    AuthenticateWithBasicAuth,
    EnsureEmailIsVerified,
    RedirectIfAuthenticated,
    RequirePassword,
    StartAuth,
    mark_password_confirmed,
)
from almasix.auth.passwords import Password
from almasix.auth.providers import ArticulateUserProvider, MemoryUserProvider

__all__ = [
    "AccessGate",
    "ArticulateUserProvider",
    "Attempting",
    "AuthManager",
    "Authenticatable",
    "AuthenticatableMixin",
    "Authenticate",
    "AuthenticateWithBasicAuth",
    "Authenticated",
    "Authorizable",
    "AuthorizationException",
    "AuthorizationResponse",
    "Authorize",
    "AuthorizesRequests",
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
