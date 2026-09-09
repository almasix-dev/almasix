"""``smith signet:prune-expired`` — delete expired personal access tokens."""

from __future__ import annotations

from datetime import timedelta

from almasix.console.command import Command
from almasix.support.helpers import now as clock_now


class SignetPruneExpiredCommand(Command):
    signature = (
        "signet:prune-expired {--hours=24 : Delete tokens expired for at least this many hours}"
    )
    description = "Delete expired personal access tokens from the database"

    async def handle(self) -> int:
        from almasix.signet.signet import Signet

        hours = int(self.option("hours") or 24)
        cutoff = clock_now() - timedelta(hours=hours)
        model = Signet.personal_access_token_model()
        tokens = (
            await model.query().where_not_null("expires_at").where("expires_at", "<=", cutoff).get()
        )
        count = 0
        for token in tokens:
            await token.delete()
            count += 1
        self.info(f"Pruned {count} expired token(s).")
        return self.SUCCESS
