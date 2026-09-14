"""Composite mail transports — failover and round-robin."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from almasix.mail.message import SentMessage


class FailoverTransport:
    """Try mailers in order until one succeeds (Laravel ``failover``)."""

    def __init__(
        self,
        resolve: Callable[[str], Any],
        mailers: list[str],
        *,
        retry_after: int = 60,
    ) -> None:
        self._resolve = resolve
        self.mailers = list(mailers)
        self.retry_after = int(retry_after)
        self._failed_until: dict[str, float] = {}

    def send(self, message: SentMessage) -> None:
        errors: list[Exception] = []
        now = time.monotonic()
        for name in self.mailers:
            until = self._failed_until.get(name, 0)
            if until > now:
                continue
            try:
                self._resolve(name).send(message)
                return
            except Exception as exc:
                self._failed_until[name] = now + self.retry_after
                errors.append(exc)
        if errors:
            raise errors[-1]
        raise RuntimeError("Failover mailer has no available transports.")


class RoundRobinTransport:
    """Rotate across mailers (Laravel ``roundrobin``)."""

    def __init__(self, resolve: Callable[[str], Any], mailers: list[str]) -> None:
        self._resolve = resolve
        self.mailers = list(mailers)
        self._index = 0

    def send(self, message: SentMessage) -> None:
        if not self.mailers:
            raise RuntimeError("Round-robin mailer has no transports.")
        errors: list[Exception] = []
        for _ in range(len(self.mailers)):
            name = self.mailers[self._index % len(self.mailers)]
            self._index += 1
            try:
                self._resolve(name).send(message)
                return
            except Exception as exc:
                errors.append(exc)
        raise errors[-1] if errors else RuntimeError("Round-robin send failed.")
