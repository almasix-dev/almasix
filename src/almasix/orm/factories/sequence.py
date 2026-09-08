"""Sequences — cycling states, Laravel's `Sequence` and `CrossJoinSequence`."""

from __future__ import annotations

import itertools
from collections.abc import Callable, Mapping
from typing import Any

#: One step of a sequence: a plain dict, or a callable given the sequence.
SequenceItem = Mapping[str, Any] | Callable[["Sequence"], Mapping[str, Any]]


class Sequence:
    """Hand out states in turn, wrapping around when the list runs out.

        Post.factory().count(6).sequence({"kind": "note"}, {"kind": "essay"})

    A callable step is given the sequence itself, so it can read `index` —
    the number of times the sequence has been called — and `count`.
    """

    def __init__(self, *sequence: SequenceItem) -> None:
        self.sequence: tuple[SequenceItem, ...] = sequence
        self.count = len(sequence)
        self.index = 0

    def __call__(self, attributes: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        del attributes
        if not self.sequence:
            return {}
        step = self.sequence[self.index % self.count]
        resolved = dict(step(self)) if callable(step) else dict(step)
        self.index += 1
        return resolved

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} {self.count} steps, at {self.index}>"


class CrossJoinSequence(Sequence):
    """Every combination of the lists it was given, in order.

        .cross_join_sequence([{"role": "admin"}, {"role": "guest"}],
                             [{"active": True}, {"active": False}])

    is four states — admin/active, admin/inactive, guest/active, guest/inactive.
    """

    def __init__(self, *sequence: list[Mapping[str, Any]]) -> None:
        combined = [
            {key: value for step in combination for key, value in step.items()}
            for combination in itertools.product(*sequence)
        ]
        super().__init__(*combined)
