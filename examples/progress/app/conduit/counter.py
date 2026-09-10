"""Progress Conduit components — counter + nested shell (M54)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from almasix.conduit import Component


class GreetingRules(BaseModel):
    label: str = Field(min_length=1, max_length=40)


class Counter(Component):
    count = 0
    label = "world"
    query_string = ["count"]
    rules = GreetingRules

    def increment(self) -> None:
        self.count += 1

    def decrement(self) -> None:
        self.count -= 1

    def reset(self) -> None:
        self.count = 0
        self.dispatch("conduit-reset", count=0)

    def save(self) -> None:
        self.validate()
        self.dispatch("conduit-saved", label=self.label)

    def render(self) -> str:
        return "conduit.counter"


class NestedShell(Component):
    title = "Nested Conduit"

    def render(self) -> str:
        return "conduit.nested"
