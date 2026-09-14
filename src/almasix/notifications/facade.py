"""Notification façade — Laravel ``Notification`` static API."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from almasix.notifications.anonymous import AnonymousNotifiable
from almasix.notifications.helpers import get_sender, notify, notify_now, set_sender


class Notification:
    """Static façade: ``Notification.send(users, InvoicePaid())``."""

    _locale: str | None = None

    @classmethod
    def send(cls, notifiables: Any, notification: Any) -> list[Any]:
        return _run(_send_many(notifiables, notification, now=False, locale=cls._locale))

    @classmethod
    def send_now(cls, notifiables: Any, notification: Any) -> list[Any]:
        return _run(_send_many(notifiables, notification, now=True, locale=cls._locale))

    @classmethod
    def locale(cls, locale: str) -> type[Notification]:
        cls._locale = locale
        return cls

    @classmethod
    def route(cls, channel: str, route: Any) -> AnonymousNotifiable:
        return AnonymousNotifiable().route(channel, route)

    @classmethod
    def fake(cls) -> Any:
        from almasix.notifications.testing import fake_notifications

        return fake_notifications()


async def _send_many(
    notifiables: Any,
    notification: Any,
    *,
    now: bool,
    locale: str | None,
) -> list[Any]:
    recipients = _normalize(notifiables)
    results: list[Any] = []
    for recipient in recipients:
        instance = notification
        if locale and hasattr(instance, "set_locale"):
            instance = instance.set_locale(locale) if instance is notification else instance
            if getattr(notification, "locale", None) is None:
                notification.locale = locale
        if now:
            results.extend(await notify_now(recipient, notification))
        else:
            results.extend(await notify(recipient, notification))
    return results


def _normalize(notifiables: Any) -> list[Any]:
    if notifiables is None:
        return []
    if isinstance(notifiables, (list, tuple, set)):
        return list(notifiables)
    if isinstance(notifiables, Iterable) and not isinstance(notifiables, (str, bytes, dict)):
        try:
            return list(notifiables)
        except TypeError:
            pass
    return [notifiables]


def _run(coro: Any) -> Any:
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


__all__ = ["Notification", "get_sender", "set_sender"]
