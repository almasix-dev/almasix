"""M56 — docs / registry / matrix stay in sync."""

from __future__ import annotations

import pathlib
import re

from almasix.validation import LARAVEL_RULES

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS = ROOT / "website" / "src" / "content" / "docs" / "validation.md"
PARITY = ROOT / "docs" / "VALIDATION_PARITY.md"


def test_docs_have_a_section_per_laravel_rule() -> None:
    text = DOCS.read_text(encoding="utf-8")
    headings = set(re.findall(r"^### ([a-z0-9_]+)\s*$", text, re.M))
    assert set(LARAVEL_RULES) <= headings


def test_parity_matrix_lists_every_rule() -> None:
    text = PARITY.read_text(encoding="utf-8")
    for name in LARAVEL_RULES:
        assert f"`{name}`" in text
        assert "**Shipped**" in text
