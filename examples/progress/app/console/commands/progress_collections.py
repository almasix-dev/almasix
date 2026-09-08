"""Demo higher order messages and lazy collections (M49)."""

from __future__ import annotations

from collections.abc import Iterator

from almasix.console.command import Command
from almasix.support import Collection, LazyCollection, collect


class Ticket:
    def __init__(self, subject: str, votes: int) -> None:
        self.subject = subject
        self.votes = votes
        self.escalated = False

    def escalate(self) -> None:
        self.escalated = True


class ProgressCollectionsCommand(Command):
    signature = "progress:collections"
    description = "Demo higher order messages + lazy collections (M49)"

    def handle(self) -> int:
        tickets: Collection = collect(
            [
                Ticket("Cannot log in", 12),
                Ticket("Slow dashboard", 3),
                Ticket("Typo on pricing", 1),
            ]
        )

        # A higher order message reads an attribute or calls a method, decided
        # by the items themselves — Python cannot tell the two apart here.
        tickets.each.escalate()
        self.info(f"votes → {tickets.sum.votes}")
        self.info(f"loudest → {tickets.sort_by_desc.votes.first().subject}")
        self.info(f"all escalated → {tickets.every.escalated}")

        # Lazy collections pull one item at a time; only the four that pass the
        # filter are ever read out of this generator.
        read: list[int] = []

        def readings() -> Iterator[int]:
            for value in range(1, 1_000_000):
                read.append(value)
                yield value

        loud = LazyCollection(readings).filter(lambda value: value % 3 == 0).take(4).all()
        self.info(f"lazy → {loud} after reading {len(read)} of a million")

        self.success("collections demo ok")
        return 0
