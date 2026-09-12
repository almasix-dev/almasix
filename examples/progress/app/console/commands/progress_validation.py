"""Demo Laravel validation parity (M56)."""

from __future__ import annotations

from almasix.console.command import Command
from almasix.validation import LARAVEL_RULES, Rule, validator


class ProgressValidationCommand(Command):
    signature = "progress:validation"
    description = "Demo request.validate DSL + Rule helpers (M56 Laravel parity)"

    def handle(self) -> int:
        self.comment("M56 — Laravel validation parity")
        self.info(f"available rules → {len(LARAVEL_RULES)}")

        dsl = validator(
            {"email": "ada@example.com", "age": 36},
            {"email": "required|email", "age": "integer|min:18"},
        )
        self.info(f"dsl validated → {dsl.validated()}")

        mixed = validator(
            {"title": "Notes"},
            {"title": [Rule.required(), Rule.min(3), Rule.max(40)]},
        )
        self.info(f"Rule.* validated → {mixed.validated()}")

        failed = validator({"email": "nope"}, {"email": "required|email"})
        self.info(f"dsl errors → {failed.errors()}")
        self.info("coverage report → htmlcov/validation (pytest --cov=almasix.validation)")
        self.success("validation demo ok")
        return 0
