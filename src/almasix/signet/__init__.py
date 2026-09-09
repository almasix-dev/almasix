"""Signet — personal access tokens and first-party SPA cookie auth.

Laravel Sanctum parity for Almasix. Client-credentials / application API keys
(not tied to a user) are intentionally out of scope — see the API Tokens docs.
"""

from __future__ import annotations

from almasix.signet.guard import SignetGuard
from almasix.signet.has_api_tokens import HasApiTokens
from almasix.signet.middleware import (
    CheckAbilities,
    CheckForAnyAbility,
    EnsureFrontendRequestsAreStateful,
)
from almasix.signet.new_access_token import NewAccessToken
from almasix.signet.personal_access_token import PersonalAccessToken
from almasix.signet.provider import SignetServiceProvider
from almasix.signet.signet import Signet, is_from_frontend, stateful_domains
from almasix.signet.transient_token import TransientToken

__all__ = [
    "CheckAbilities",
    "CheckForAnyAbility",
    "EnsureFrontendRequestsAreStateful",
    "HasApiTokens",
    "NewAccessToken",
    "PersonalAccessToken",
    "Signet",
    "SignetGuard",
    "SignetServiceProvider",
    "TransientToken",
    "is_from_frontend",
    "stateful_domains",
]
