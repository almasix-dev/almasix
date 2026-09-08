"""M11 smoke — sync job dispatch in progress app."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from almasix.console.kernel import ConsoleKernel
from almasix.queue import Job, dispatch_sync
from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke, pytest.mark.regression]

PROGRESS = Path(__file__).resolve().parents[2] / "examples" / "progress"


class SmokeJob(Job):
    ran = False

    def handle(self) -> None:
        SmokeJob.ran = True


@pytest.fixture()
def progress_cwd(monkeypatch: pytest.MonkeyPatch) -> Path:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    yield PROGRESS
    purge_generated_app_modules()
    while str(PROGRESS) in sys.path:
        sys.path.remove(str(PROGRESS))


@pytest.mark.asyncio
async def test_m11_sync_dispatch(progress_cwd: Path) -> None:
    ConsoleKernel.from_cwd(progress_cwd)
    SmokeJob.ran = False
    await dispatch_sync(SmokeJob())
    assert SmokeJob.ran is True


def test_m11_queue_commands_registered(progress_cwd: Path) -> None:
    kernel = ConsoleKernel.from_cwd(progress_cwd)
    for name in ("queue:work", "queue:listen", "queue:failed", "queue:retry"):
        assert name in kernel.commands
