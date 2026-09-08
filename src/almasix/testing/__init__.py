"""Almasix's testing toolkit — Laravel's Testing chapter, spelled for pytest.

    from almasix.testing import TestCase

    class TestPosts(TestCase):
        async def test_the_index_lists_posts(self):
            response = await self.get("/posts")
            response.assert_ok().assert_see("Hello")

Everything here is optional: the framework's own suite is plain pytest, and so
is an application's. What this package adds is the vocabulary — a client that
drives the real middleware stack, assertions that explain themselves, console
commands that answer their own questions, and one door to every fake.
"""

from __future__ import annotations

from almasix.filesystem.testing import FakeDisk, fake_disk
from almasix.notifications.testing import (
    FakeNotifications,
    RecordedNotification,
    fake_notifications,
)
from almasix.queue.testing import FakeQueue, RecordedJob, fake_queue
from almasix.testing.case import TestCase, boot_application
from almasix.testing.client import TestClient
from almasix.testing.console import AnswerSink, PendingCommand, artisan
from almasix.testing.database import (
    assert_database_count,
    assert_database_empty,
    assert_database_has,
    assert_database_missing,
    assert_model_exists,
    assert_model_missing,
    assert_not_soft_deleted,
    assert_soft_deleted,
    database_transactions,
    refresh_database,
)
from almasix.testing.fakes import fake, fakeable, restore_fakes
from almasix.testing.middleware import with_middleware, without_middleware
from almasix.testing.response import TestResponse
from almasix.testing.time import (
    TimeTraveller,
    freeze_time,
    frozen_time,
    travel,
    travel_back,
    travel_to,
)

__all__ = [
    "AnswerSink",
    "FakeDisk",
    "FakeNotifications",
    "FakeQueue",
    "PendingCommand",
    "RecordedJob",
    "RecordedNotification",
    "TestCase",
    "TestClient",
    "TestResponse",
    "TimeTraveller",
    "artisan",
    "assert_database_count",
    "assert_database_empty",
    "assert_database_has",
    "assert_database_missing",
    "assert_model_exists",
    "assert_model_missing",
    "assert_not_soft_deleted",
    "assert_soft_deleted",
    "boot_application",
    "database_transactions",
    "fake",
    "fake_disk",
    "fake_notifications",
    "fake_queue",
    "fakeable",
    "freeze_time",
    "frozen_time",
    "refresh_database",
    "restore_fakes",
    "travel",
    "travel_back",
    "travel_to",
    "with_middleware",
    "without_middleware",
]
