"""Shared test setup — one application, and fakes that clean up."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from almasix.testing import restore_fakes


@pytest.fixture(autouse=True)
def _no_fake_outlives_its_test() -> Iterator[None]:
    """A faked mailer or queue must not still be installed for the next test."""
    yield
    restore_fakes()
