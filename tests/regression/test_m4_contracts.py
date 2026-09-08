"""M4 regression — public translation contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

import almasix.translation
from almasix.installer.scaffold import scaffold_app

pytestmark = pytest.mark.regression


def test_translation_exports() -> None:
    for name in (
        "Translator",
        "Lang",
        "Number",
        "SetLocaleMiddleware",
        "TranslationServiceProvider",
        "__",
        "trans",
        "trans_choice",
        "get_locale",
        "set_locale",
        "is_locale",
        "localize_date",
    ):
        assert name in almasix.translation.__all__
        assert hasattr(almasix.translation, name)


def test_scaffold_declares_locale_and_lang_tree(tmp_path: Path) -> None:
    root = scaffold_app("m4_contract", destination=tmp_path / "m4_contract")
    assert (root / "lang" / "en" / "messages.py").is_file()
    assert "APP_LOCALE=" in (root / ".env").read_text(encoding="utf-8")
    bootstrap = (root / "bootstrap" / "app.py").read_text(encoding="utf-8")
    assert "SetLocaleMiddleware" in bootstrap
    assert "locale" in bootstrap
