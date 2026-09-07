"""Authorization — Gates, Policies, and related helpers."""

from __future__ import annotations

from avalon.auth.access.authorizable import Authorizable
from avalon.auth.access.exceptions import AuthorizationException
from avalon.auth.access.facade import Gate
from avalon.auth.access.gate import CONTROLLER_RESOURCE_ABILITIES, RESOURCE_ABILITIES, Gate as AccessGate
from avalon.auth.access.handles import HandlesAuthorization
from avalon.auth.access.helpers import authorize, gate, gate_allows, gate_any
from avalon.auth.access.middleware import Authorize
from avalon.auth.access.policy import Policy
from avalon.auth.access.requests import AuthorizesRequests
from avalon.auth.access.response import AuthorizationResponse

__all__ = [
    "AccessGate",
    "Authorizable",
    "AuthorizationException",
    "AuthorizationResponse",
    "AuthorizesRequests",
    "Authorize",
    "CONTROLLER_RESOURCE_ABILITIES",
    "Gate",
    "HandlesAuthorization",
    "Policy",
    "RESOURCE_ABILITIES",
    "authorize",
    "gate",
    "gate_allows",
    "gate_any",
]
