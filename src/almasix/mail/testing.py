"""Mail testing assertions for the array transport."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from almasix.mail.mailer import Mail
from almasix.mail.message import SentMessage
from almasix.mail.transports.array import ArrayTransport


class MailAssertions:
    """Laravel-style mail fakes backed by the array driver."""

    def __init__(self, mailer: str = "array") -> None:
        self.mailer_name = mailer

    @property
    def transport(self) -> ArrayTransport:
        transport = Mail.manager().array_transport(self.mailer_name)
        if transport is None:
            raise RuntimeError(
                f"Mailer [{self.mailer_name}] is not using the array transport."
            )
        return transport

    def flush(self) -> None:
        self.transport.flush()

    def sent(self) -> list[SentMessage]:
        return list(self.transport.sent_messages)

    def queued(self) -> list[SentMessage]:
        return list(self.transport.queued_messages)

    def assert_sent(
        self,
        mailable: type[Any] | str,
        callback: Callable[[SentMessage], None] | None = None,
    ) -> SentMessage:
        matches = self._filter(self.sent(), mailable)
        if not matches:
            expected = mailable if isinstance(mailable, str) else mailable.__name__
            raise AssertionError(f"No mailable of type [{expected}] was sent.")
        message = matches[-1]
        if callback is not None:
            callback(message)
        return message

    def assert_not_sent(self, mailable: type[Any] | str | None = None) -> None:
        messages = self.sent()
        if mailable is None:
            if messages:
                raise AssertionError(f"Expected no mail to be sent, but {len(messages)} were sent.")
            return
        if self._filter(messages, mailable):
            expected = mailable if isinstance(mailable, str) else mailable.__name__
            raise AssertionError(f"Mailable [{expected}] was sent unexpectedly.")

    def assert_nothing_sent(self) -> None:
        self.assert_not_sent(None)

    def assert_queued(
        self,
        mailable: type[Any] | str,
        callback: Callable[[SentMessage], None] | None = None,
    ) -> SentMessage:
        matches = self._filter(self.queued(), mailable)
        if not matches:
            expected = mailable if isinstance(mailable, str) else mailable.__name__
            raise AssertionError(f"No mailable of type [{expected}] was queued.")
        message = matches[-1]
        if callback is not None:
            callback(message)
        return message

    def assert_not_queued(self, mailable: type[Any] | str | None = None) -> None:
        messages = self.queued()
        if mailable is None:
            if messages:
                raise AssertionError(
                    f"Expected no mail to be queued, but {len(messages)} were queued."
                )
            return
        if self._filter(messages, mailable):
            expected = mailable if isinstance(mailable, str) else mailable.__name__
            raise AssertionError(f"Mailable [{expected}] was queued unexpectedly.")

    def assert_nothing_queued(self) -> None:
        self.assert_not_queued(None)

    @staticmethod
    def _filter(messages: list[SentMessage], mailable: type[Any] | str) -> list[SentMessage]:
        if isinstance(mailable, str):
            return [item for item in messages if type(item.mailable).__name__ == mailable]
        return [item for item in messages if isinstance(item.mailable, mailable)]
