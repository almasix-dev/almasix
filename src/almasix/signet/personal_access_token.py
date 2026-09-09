"""Personal access token model — Signet's ``personal_access_tokens`` table."""

from __future__ import annotations

import hashlib
from datetime import datetime

from almasix.orm import Model
from almasix.support.helpers import now as clock_now


class PersonalAccessToken(Model):
    """Hashed API token owned by a tokenable (typically ``User``)."""

    table = "personal_access_tokens"
    fillable = (
        "name",
        "token",
        "abilities",
        "expires_at",
        "tokenable_type",
        "tokenable_id",
    )
    casts = {
        "abilities": "array",
        "last_used_at": "datetime",
        "expires_at": "datetime",
    }
    hidden = ("token",)

    @classmethod
    async def find_token(cls, token: str) -> PersonalAccessToken | None:
        """Resolve a Bearer plain-text token to a row (Laravel ``findToken``)."""
        if not token:
            return None
        if "|" not in token:
            hashed = _hash_token(token)
            return await cls.query().where("token", "=", hashed).first()  # type: ignore[return-value]

        token_id, _, plain = token.partition("|")
        if not token_id or not plain:
            return None
        instance = await cls.query().find(token_id)
        if instance is None:
            return None
        stored = str(instance.get_raw_attribute("token") or "")
        if not _hash_equals(stored, _hash_token(plain)):
            return None
        return instance  # type: ignore[return-value]

    def can(self, ability: str) -> bool:
        abilities = self._abilities_list()
        return "*" in abilities or ability in abilities

    def cant(self, ability: str) -> bool:
        return not self.can(ability)

    def _abilities_list(self) -> list[str]:
        raw = self.get_attribute("abilities")
        if raw is None:  # pragma: no cover - cast usually yields list
            return []
        if isinstance(raw, (list, tuple)):
            return [str(item) for item in raw]
        return []  # pragma: no cover - cast yields list/None

    def is_expired(self) -> bool:
        expires = self.get_attribute("expires_at")
        if expires is None:
            return False
        if not isinstance(expires, datetime):  # pragma: no cover - cast yields datetime
            return False
        current = clock_now()
        # Compare aware/naive safely by stripping tz if needed.
        if expires.tzinfo is not None and current.tzinfo is None:  # pragma: no cover
            expires = expires.replace(tzinfo=None)
        elif expires.tzinfo is None and current.tzinfo is not None:  # pragma: no cover
            current = current.replace(tzinfo=None)
        return expires <= current

    async def touch_last_used(self) -> None:
        self.set_attribute("last_used_at", clock_now())
        await self.save()

    def tokenable(self):
        from almasix.orm.relations import MorphTo

        return MorphTo(self, "tokenable")


def _hash_token(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def _hash_equals(left: str, right: str) -> bool:
    if len(left) != len(right):  # pragma: no cover - lengths match for SHA-256 digests
        return False
    result = 0
    for a, b in zip(left, right, strict=True):
        result |= ord(a) ^ ord(b)
    return result == 0
