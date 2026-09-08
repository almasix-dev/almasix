"""Authorization — Gates, Policies, and related helpers."""

from __future__ import annotations

from almasix.auth.access.authorizable import Authorizable
from almasix.auth.access.exceptions import AuthorizationException
from almasix.auth.access.facade import Gate
from almasix.auth.access.gate import CONTROLLER_RESOURCE_ABILITIES, RESOURCE_ABILITIES
from almasix.auth.access.gate import Gate as AccessGate
from almasix.auth.access.handles import HandlesAuthorization
from almasix.auth.access.helpers import authorize, gate, gate_allows, gate_any, policy
from almasix.auth.access.middleware import Authorize
from almasix.auth.access.policies import Policy
from almasix.auth.access.requests import AuthorizesRequests
from almasix.auth.access.response import AuthorizationResponse

__all__ = [
    "CONTROLLER_RESOURCE_ABILITIES",
    "RESOURCE_ABILITIES",
    "AccessGate",
    "Authorizable",
    "AuthorizationException",
    "AuthorizationResponse",
    "Authorize",
    "AuthorizesRequests",
    "Gate",
    "HandlesAuthorization",
    "Policy",
    "authorize",
    "gate",
    "gate_allows",
    "gate_any",
    "policy",
]
