"""The guard destructive commands ask before they destroy anything.

Laravel's ``ConfirmableTrait``, with one difference: Laravel only stops to ask
in production, while a command that deletes jobs or drops tables asks wherever
it runs. ``--force`` is the way past it, and in production it is the only way.
"""

from __future__ import annotations

from typing import Any


def current_environment(default: str = "production") -> str:
    """``config('app.env')`` — ``default`` when there is nothing to read.

    Guessing "production" is the safe guess for a command that destroys
    something: the worst it can do is refuse.
    """
    from almasix.config import config

    try:
        return str(config("app.env", default) or default)
    except Exception:  # noqa: BLE001 - config is absent outside a booted app
        return default


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

    def confirm_in_production(self: Any) -> bool:
        """Laravel's guard as written: nothing is asked outside production.

        A command that only writes what you asked it to write — `migrate`,
        say — has no reason to stop and check on a laptop, and every reason
        to stop on a production database.
        """
        # Outside an application there is no production database to protect,
        # so a missing config is not read as one here.
        if self.option("force") or current_environment("local") != "production":
            return True
        self.error(
            "Application is in production. Re-run with --force if you really mean it."
        )
        return False
