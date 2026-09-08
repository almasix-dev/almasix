"""A unit test — no application, no database, no HTTP."""

from __future__ import annotations

from datetime import UTC, datetime

from almasix.support import Str
from almasix.support.helpers import now
from almasix.testing import frozen_time


class ExampleTest:
    def test_a_slug_is_a_slug(self) -> None:
        assert Str.slug("Hello There") == "hello-there"

    def test_the_clock_can_be_held_still(self) -> None:
        with frozen_time(datetime(2030, 1, 1, tzinfo=UTC)):
            assert now().year == 2030
