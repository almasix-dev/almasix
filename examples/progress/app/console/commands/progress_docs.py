"""Demo the docs journey rewrite + Prologue (M39).

Checks teaching-order Basics, Prologue pages, no milestone IDs in Starlight
content, and the header version switcher.
"""

from __future__ import annotations

import re
from pathlib import Path

from almasix.console.command import Command

ROOT = Path(__file__).resolve().parents[5]
DOCS = ROOT / "website" / "src" / "content" / "docs"
ASTRO = ROOT / "website" / "astro.config.mjs"
HEADER = ROOT / "website" / "src" / "components" / "Header.astro"
VERSION_SELECT = ROOT / "website" / "src" / "components" / "VersionSelect.astro"

# Teaching order from docs/PLAN.md (API Resources sits after Responses).
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

PROLOGUE = [
    "prologue/introduction",
    "prologue/release-notes",
    "prologue/upgrade",
    "prologue/versions",
]

MILESTONE_RE = re.compile(r"\bM\d{1,2}\b")


class ProgressDocsCommand(Command):
    signature = "progress:docs"
    description = (
        "Demo docs journey — Prologue, Basics order, no milestone IDs, version switcher (M39)"
    )

    def handle(self) -> int:
        config = ASTRO.read_text(encoding="utf-8")
        if "label: 'Prologue'" not in config and 'label: "Prologue"' not in config:
            self.error("astro.config.mjs missing Prologue sidebar group")
            return 1
        self.info("Prologue sidebar -> present")

        for slug in PROLOGUE:
            path = DOCS / f"{slug}.md"
            if not path.is_file():
                self.error(f"missing {path.relative_to(ROOT)}")
                return 1
        self.info("Prologue pages -> introduction, release-notes, upgrade, versions")

        # Extract Basics slugs in sidebar order.
        basics_block = re.search(
            r"label:\s*['\"]The Basics['\"][\s\S]*?items:\s*\[([\s\S]*?)\]\s*,",
            config,
        )
        if not basics_block:
            self.error("could not parse The Basics sidebar block")
            return 1
        # Stop at the first items array only (nested groups use items too later).
        slugs = re.findall(r"slug:\s*['\"]([^'\"]+)['\"]", basics_block.group(1))
        # Nested Document groups live under Articulate, not Basics — Basics has no nesting.
        if slugs != BASICS_ORDER:
            self.error("Basics teaching order mismatch")
            self.line(f"  expected: {BASICS_ORDER}")
            self.line(f"  actual:   {slugs}")
            return 1
        self.info("Basics teaching order -> routing … rate-limiting")

        if "authentication" not in slugs:
            self.error("Authentication must live under The Basics")
            return 1
        self.info("Authentication -> in The Basics (after Session)")

        offenders: list[str] = []
        for path in sorted(DOCS.rglob("*")):
            if path.suffix not in {".md", ".mdx"}:
                continue
            text = path.read_text(encoding="utf-8")
            if MILESTONE_RE.search(text):
                offenders.append(str(path.relative_to(ROOT)))
        if offenders:
            self.error("milestone IDs still appear in user-facing docs:")
            for item in offenders:
                self.line(f"  {item}")
            return 1
        self.info("user docs -> no milestone IDs (M##)")

        if not VERSION_SELECT.is_file() or not (ROOT / "website" / "src" / "versions.mjs").is_file():
            self.error("Header / VersionSelect / versions.mjs missing")
            return 1
        header = HEADER.read_text(encoding="utf-8")
        if "VersionSelect" not in header:
            self.error("Header does not include VersionSelect")
            return 1
        version_src = VERSION_SELECT.read_text(encoding="utf-8")
        versions_mjs = (ROOT / "website" / "src" / "versions.mjs").read_text(encoding="utf-8")
        if "LATEST_VERSION = '0.x'" not in versions_mjs and 'LATEST_VERSION = "0.x"' not in versions_mjs:
            self.error("versions.mjs must set LATEST_VERSION to 0.x (never main)")
            return 1
        if "0.x" not in versions_mjs or "DOCS_VERSIONS" not in versions_mjs:
            self.error("versions.mjs must list major 0.x plus main")
            return 1
        if "'main'" not in versions_mjs and '"main"' not in versions_mjs:
            self.error("versions.mjs must include main as an opt-in line")
            return 1
        if re.search(r"data-version=['\"]0\.\d['\"]", version_src):
            self.error("VersionSelect must not list minor releases")
            return 1
        if "syncFromLocation" not in version_src:
            self.error("VersionSelect must sync selection from the live URL")
            return 1
        if "data-latest-link" not in version_src:
            self.error("VersionSelect must not rewrite the banner's switch-to-latest link")
            return 1
        if "main" not in version_src:
            self.error("VersionSelect must include main")
            return 1
        banner = ROOT / "website" / "src" / "components" / "VersionBanner.astro"
        banner_text = " ".join(banner.read_text(encoding="utf-8").split())
        if not banner.is_file() or "not the latest version" not in banner_text:
            self.error("VersionBanner missing older-docs warning")
            return 1
        if "display: none" not in banner.read_text(encoding="utf-8"):
            self.error("VersionBanner must default to display:none (not flex overriding hidden)")
            return 1
        frame = (ROOT / "website" / "src" / "components" / "PageFrame.astro").read_text(
            encoding="utf-8"
        )
        if "VersionBanner" not in frame:
            self.error("PageFrame must mount VersionBanner")
            return 1
        self.info("version switcher -> latest major + main; older-docs banner")

        self.success("docs journey + Prologue ok")
        return 0
