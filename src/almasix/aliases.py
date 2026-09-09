"""Laravel's camelCase spelling for snake_case fluent APIs.

Almasix writes `where_number` because that is what Python reads like, and
Laravel writes `whereNumber`. Rather than hand-writing two of every method,
these walk a class once and alias what is already there — so a method added
later gets its camelCase spelling for free, and the two can never disagree.
"""

from __future__ import annotations

import re

_SNAKE_PART = re.compile(r"_(\w)")


def camel_case(name: str) -> str:
    """``where_number`` -> ``whereNumber``."""
    return _SNAKE_PART.sub(lambda match: match.group(1).upper(), name)


def install_camel_aliases(cls: type) -> None:
    """Add Laravel's camelCase spelling for every fluent method on ``cls``.

    Only the class's own methods, and only where the camelCase name is free:
    an inherited or hand-written spelling wins, which is how a deliberate
    difference survives.
    """
    for name, member in list(vars(cls).items()):
        if name.startswith("_") or "_" not in name:
            continue
        camel = camel_case(name)
        if not hasattr(cls, camel):
            setattr(cls, camel, member)
