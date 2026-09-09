"""Indexing that waits for the transaction, and the tests that wait for it."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

#: Index writes started after a commit and not yet finished. Holding the tasks
#: keeps them from being garbage collected mid-flight.
_pending: set[asyncio.Task[Any]] = set()


def defer_until_commit(model: Any, work: Callable[[], Any]) -> bool:
    """Park an index write on the current transaction; say whether we did.

    `False` means there was no transaction to wait for and the caller should
    write to the index as usual.
    """
    try:
        from almasix.orm.facade import get_manager

        connection = get_manager().connection(type(model).connection)
    except Exception:
        return False
    if not connection.in_transaction():
        return False

    connection.after_commit(lambda: _run(work()))
    return True


def _run(coroutine: Any) -> None:
    """Run a coroutine from the synchronous after-commit callback."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # pragma: no cover - a commit outside a loop cannot happen
        asyncio.run(coroutine)
        return
    task = loop.create_task(coroutine)
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def flush_search() -> None:
    """Wait for every index write a commit set going.

    Committing hands the write to the loop and returns, which is what you
    want in a request and not what you want in a test that is about to
    assert on the index.
    """
    while _pending:
        await asyncio.gather(*list(_pending), return_exceptions=True)
