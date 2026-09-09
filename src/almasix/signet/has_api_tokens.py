"""``HasApiTokens`` mixin — issue, inspect, and revoke personal access tokens."""

from __future__ import annotations

import secrets
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from almasix.orm import relation
from almasix.signet.new_access_token import NewAccessToken
from almasix.signet.personal_access_token import PersonalAccessToken, _hash_token
from almasix.signet.transient_token import TransientToken


class HasApiTokens:
    """Laravel ``HasApiTokens`` — mix into your authenticatable model."""

    _access_token: PersonalAccessToken | TransientToken | None = None

    @relation
    def tokens(self):
        from almasix.signet.signet import Signet

        return self.morph_many(Signet.personal_access_token_model(), "tokenable")  # type: ignore[attr-defined]

    async def create_token(
        self,
        name: str,
        abilities: Sequence[str] | None = None,
        expires_at: datetime | None = None,
    ) -> NewAccessToken:
        """Create a hashed PAT; return the one-time plain-text token."""
        from datetime import timedelta

        from almasix.orm.morph import morph_map
        from almasix.support.helpers import now as clock_now

        # Ensure short morph aliases resolve back to this model when authenticating.
        owner = type(self)
        morph_map(
            {
                owner.__name__: owner,
                f"{owner.__module__}.{owner.__qualname__}": owner,
            }
        )

        plain = self._generate_token_string()
        resolved_expires = expires_at
        if resolved_expires is None:
            try:
                from almasix.config import config

                minutes = config("signet.expiration")
                if minutes is not None and str(minutes).strip() != "":
                    resolved_expires = clock_now() + timedelta(minutes=int(minutes))
            except Exception:
                resolved_expires = None
        token = await self.tokens().create(  # type: ignore[attr-defined]
            {
                "name": name,
                "token": _hash_token(plain),
                "abilities": list(abilities) if abilities is not None else ["*"],
                "expires_at": resolved_expires,
            }
        )
        return NewAccessToken(token, f"{token.get_key()}|{plain}")

    def current_access_token(self) -> PersonalAccessToken | TransientToken | None:
        return getattr(self, "_access_token", None)

    def with_access_token(self, access_token: PersonalAccessToken | TransientToken) -> Any:
        self._access_token = access_token
        return self

    def token_can(self, ability: str) -> bool:
        """Whether the current access token has ``ability``.

        First-party SPA session auth (no PAT) always returns ``True``, matching
        Laravel Sanctum — policies still decide authorization.
        """
        token = self.current_access_token()
        if token is None:
            return True
        return token.can(ability)

    def token_cant(self, ability: str) -> bool:
        return not self.token_can(ability)

    async def tokens_delete(self) -> int:
        """Revoke every token for this user."""
        deleted = 0
        for token in await self.tokens().get():  # type: ignore[attr-defined]
            await token.delete()
            deleted += 1
        return deleted

    def _generate_token_string(self) -> str:
        return secrets.token_hex(20)
