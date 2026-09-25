"""Demo the docs journey rewrite + Prologue (M39).

Checks teaching-order Basics, Prologue pages, no milestone IDs in Starlight
content, and the header version switcher (wired via ``@almasix/starlight-theme``
``headerExtras`` / ``pageBanner``).
"""

from __future__ import annotations

import re
from pathlib import Path

from almasix.console.command import Command

ROOT = Path(__file__).resolve().parents[5]
DOCS = ROOT / "website" / "src" / "content" / "docs"
ASTRO = ROOT / "website" / "astro.config.mjs"
VERSION_SELECT = ROOT / "website" / "src" / "components" / "VersionSelect.astro"
VERSION_BANNER = ROOT / "website" / "src" / "components" / "VersionBanner.astro"
VERSIONS_MJS = ROOT / "website" / "src" / "versions.mjs"

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
    "prologue/compared",
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
        self.info(
            "Prologue pages -> introduction, compared, release-notes, upgrade, versions"
        )

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

        if not VERSION_SELECT.is_file() or not VERSIONS_MJS.is_file():
            self.error("VersionSelect / versions.mjs missing")
            return 1
        if "headerExtras: './src/components/VersionSelect.astro'" not in config:
            self.error("astro.config must wire VersionSelect via headerExtras")
            return 1
        if "pageBanner: './src/components/VersionBanner.astro'" not in config:
            self.error("astro.config must wire VersionBanner via pageBanner")
            return 1
        version_src = VERSION_SELECT.read_text(encoding="utf-8")
        versions_mjs = VERSIONS_MJS.read_text(encoding="utf-8")
        if (
            "LATEST_VERSION = '0.x'" not in versions_mjs
            and 'LATEST_VERSION = "0.x"' not in versions_mjs
        ):
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
        if "main" not in version_src and "main" not in versions_mjs:
            self.error("VersionSelect / versions.mjs must include main")
            return 1
        if not VERSION_BANNER.is_file():
            self.error("VersionBanner missing")
            return 1
        banner_text = " ".join(VERSION_BANNER.read_text(encoding="utf-8").split())
        if "not the latest version" not in banner_text:
            self.error("VersionBanner missing older-docs warning")
            return 1
        if "display: none" not in VERSION_BANNER.read_text(encoding="utf-8"):
            self.error("VersionBanner must default to display:none (not flex overriding hidden)")
            return 1
        self.info("version switcher -> latest major + main; older-docs banner")

        self.success("docs journey + Prologue ok")
        return 0
