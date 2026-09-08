"""M10 smoke — Storage against progress local disk."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from almasix.console.kernel import ConsoleKernel
from almasix.filesystem import Storage
from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke, pytest.mark.regression]

PROGRESS = Path(__file__).resolve().parents[2] / "examples" / "progress"


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


def test_m10_storage_put_get(progress_cwd: Path) -> None:
    kernel = ConsoleKernel.from_cwd(progress_cwd)
    del kernel
    Storage.put("smoke/m10.txt", "ok")
    assert Storage.exists("smoke/m10.txt")
    assert Storage.get("smoke/m10.txt") == b"ok"
    Storage.delete("smoke/m10.txt")


def test_m10_storage_link_command(progress_cwd: Path) -> None:
    kernel = ConsoleKernel.from_cwd(progress_cwd)
    code = kernel.run_command("storage:link", options={"relative": True, "force": True})
    assert code == 0
    assert (progress_cwd / "public" / "storage").exists()
