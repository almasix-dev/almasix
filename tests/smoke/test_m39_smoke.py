"""M39 smoke — Prologue, Basics order, no milestone IDs, version switcher, demo."""

from __future__ import annotations

import importlib
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke]

PROGRESS = Path(__file__).resolve().parents[2] / "examples" / "progress"
ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "website" / "src" / "content" / "docs"

BASICS_ORDER = [
    "routing",
    "controllers",
    "requests",
    "responses",
    "api-resources",
    "middleware",
    "csrf",
    "validation",
    "views",
    "asset-bundling",
    "urls",
    "session",
    "authentication",
    "hashing",
    "passwords",
    "errors",
    "logging",
    "security",
    "rate-limiting",
]


@pytest.fixture()
def progress_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    module = importlib.import_module("bootstrap.app")
    return TestClient(module.asgi)


def test_m39_prologue_pages_exist() -> None:
    for slug in (
        "prologue/introduction",
        "prologue/release-notes",
        "prologue/upgrade",
        "prologue/versions",
    ):
        assert (DOCS / f"{slug}.md").is_file(), slug


def test_m39_basics_teaching_order() -> None:
    config = (ROOT / "website" / "astro.config.mjs").read_text(encoding="utf-8")
    assert "label: 'Prologue'" in config
    basics_block = re.search(
        r"label:\s*['\"]The Basics['\"][\s\S]*?items:\s*\[([\s\S]*?)\]\s*,",
        config,
    )
    assert basics_block is not None
    slugs = re.findall(r"slug:\s*['\"]([^'\"]+)['\"]", basics_block.group(1))
    assert slugs == BASICS_ORDER
    assert "authentication" in slugs


def test_m39_no_milestone_ids_in_user_docs() -> None:
    pattern = re.compile(r"\bM\d{1,2}\b")
    offenders = []
    for path in DOCS.rglob("*"):
        if path.suffix not in {".md", ".mdx"}:
            continue
        if pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_m39_version_switcher_in_header() -> None:
    header = (ROOT / "website" / "src" / "components" / "Header.astro").read_text(encoding="utf-8")
    select = (ROOT / "website" / "src" / "components" / "VersionSelect.astro").read_text(
        encoding="utf-8"
    )
    versions = (ROOT / "website" / "src" / "versions.mjs").read_text(encoding="utf-8")
    banner = (ROOT / "website" / "src" / "components" / "VersionBanner.astro").read_text(
        encoding="utf-8"
    )
    banner_flat = " ".join(banner.split())
    frame = (ROOT / "website" / "src" / "components" / "PageFrame.astro").read_text(
        encoding="utf-8"
    )
    astro = (ROOT / "website" / "astro.config.mjs").read_text(encoding="utf-8")
    assert "VersionSelect" in header
    assert "LATEST_VERSION = '0.x'" in versions or 'LATEST_VERSION = "0.x"' in versions
    assert "main" in versions
    assert "0.x" in versions
    assert "syncFromLocation" in select
    assert "data-latest-link" in select
    assert not re.search(r"data-version=['\"]0\.\d['\"]", select)
    assert "not the latest version" in banner_flat
    assert "VersionBanner" in frame
    assert "PageFrame: './src/components/PageFrame.astro'" in astro


def test_m39_demo_command_runs() -> None:
    result = subprocess.run(
        [sys.executable, "smith", "progress:docs"],
        cwd=PROGRESS,
        capture_output=True,
        text=True,
        check=False,
    )
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    for line in (
        "Prologue sidebar -> present",
        "Prologue pages -> introduction, release-notes, upgrade, versions",
        "Basics teaching order -> routing … rate-limiting",
        "user docs -> no milestone IDs (M##)",
        "version switcher -> latest major + main; older-docs banner",
        "docs journey + Prologue ok",
    ):
        assert line in out, line


def test_m39_board_marks_docs_complete(progress_client: TestClient) -> None:
    board = progress_client.get("/api/progress").json()
    by_id = {milestone["id"]: milestone for milestone in board["milestones"]}
    assert by_id["M39"]["status"] == "complete"
    assert "smith progress:docs" in by_id["M39"]["proof"]
    assert any("Prologue" in item for item in by_id["M39"]["proof"])


def test_m39_readme_lists_docs_demo() -> None:
    readme = (PROGRESS / "README.md").read_text(encoding="utf-8")
    assert "smith progress:docs" in readme
    assert "**M39**" in readme
