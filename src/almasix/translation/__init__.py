"""Localization — Laravel-parity translator, plurals, Number helpers."""

from almasix.translation.dates import localize_date, localize_time
from almasix.translation.helpers import (
    Lang,
    __,
    get_translator,
    set_translator,
    trans,
    trans_choice,
)
from almasix.translation.locale import (
    get_fallback_locale,
    get_locale,
    is_locale,
    set_fallback_locale,
    set_locale,
)
from almasix.translation.middleware import SetLocaleMiddleware
from almasix.translation.number import Number
from almasix.translation.provider import TranslationServiceProvider, framework_lang_path
from almasix.translation.translator import Translator

__all__ = [
    "Lang",
    "Number",
    "SetLocaleMiddleware",
    "TranslationServiceProvider",
    "Translator",
    "__",
    "framework_lang_path",
    "get_fallback_locale",
    "get_locale",
    "get_translator",
    "is_locale",
    "localize_date",
    "localize_time",
    "set_fallback_locale",
    "set_locale",
    "set_translator",
    "trans",
    "trans_choice",
]
