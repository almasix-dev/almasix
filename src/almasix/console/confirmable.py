"""The guard destructive commands ask before they destroy anything.

Laravel's ``ConfirmableTrait``, with one difference: Laravel only stops to ask
in production, while a command that deletes jobs or drops tables asks wherever
it runs. ``--force`` is the way past it, and in production it is the only way.
"""

from __future__ import annotations

from typing import Any


def current_environment() -> str:
    """``config('app.env')`` — ``production`` when there is nothing to read.

    Guessing "production" is the safe guess: the worst it can do is refuse.
    """
    from almasix.config import config

    try:
        return str(config("app.env", "production") or "production")
    except Exception:  # noqa: BLE001 - config is absent outside a booted app
        return "production"


class Confirmable:
    """Mixin giving a command a ``--force``-able confirmation step."""

    def confirm_to_proceed(self: Any, warning: str) -> bool:
        """``True`` when the command may go ahead. Says why when it may not."""
        if self.option("force"):
            return True

        environment = current_environment()
        if environment == "production":
            self.error(
                f"Application is in production ({environment}). "
                "Re-run with --force if you really mean it."
            )
            return False

        self.warn(warning)
        if not self.confirm("Do you wish to continue?"):
            self.comment("Nothing was changed.")
            return False
        return True
