"""Helpers and Lang façade over the bound Translator."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from almasix.translation.translator import Translator

_translator: Translator | None = None


def set_translator(translator: Translator | None) -> None:
    global _translator
    _translator = translator


def get_translator() -> Translator:
    global _translator
    if _translator is None:
        # Framework-only default so validation can resolve messages before boot.
        from almasix.translation.provider import framework_lang_path

        _translator = Translator()
        _translator.add_path(framework_lang_path())
        _translator.add_json_path(framework_lang_path())
    return _translator


def __(
    key: str,
    replace: Mapping[str, Any] | None = None,
    locale: str | None = None,
) -> str:
    result = get_translator().get(key, replace, locale)
    return result if isinstance(result, str) else str(result)


def trans(
    key: str,
    replace: Mapping[str, Any] | None = None,
    locale: str | None = None,
) -> str:
    return __(key, replace, locale)


def trans_choice(
    key: str,
    number: float,
    replace: Mapping[str, Any] | None = None,
    locale: str | None = None,
) -> str:
    return get_translator().choice(key, number, replace, locale)


class Lang:
    """Static façade mirroring Laravel's `Lang` / `Illuminate\\Support\\Facades\\Lang`."""

    @staticmethod
    def get(
        key: str,
        replace: Mapping[str, Any] | None = None,
        locale: str | None = None,
        *,
        fallback: bool = True,
    ) -> Any:
        return get_translator().get(key, replace, locale, fallback=fallback)

    @staticmethod
    def has(key: str, locale: str | None = None, *, fallback: bool = True) -> bool:
        return get_translator().has(key, locale, fallback=fallback)

    @staticmethod
    def has_for_locale(key: str, locale: str | None = None) -> bool:
        return get_translator().has_for_locale(key, locale)

    @staticmethod
    def choice(
        key: str,
        number: float,
        replace: Mapping[str, Any] | None = None,
        locale: str | None = None,
    ) -> str:
        return get_translator().choice(key, number, replace, locale)

    @staticmethod
    def add_lines(lines: dict[str, Any], locale: str, namespace: str = "*") -> None:
        get_translator().add_lines(lines, locale, namespace)

    @staticmethod
    def add_namespace(namespace: str, hint: str | Path) -> None:
        get_translator().add_namespace(namespace, hint)

    @staticmethod
    def add_path(path: str | Path) -> None:
        get_translator().add_path(path)

    @staticmethod
    def add_json_path(path: str | Path) -> None:
        get_translator().add_json_path(path)

    @staticmethod
    def handle_missing_keys_using(
        callback: Callable[[str, str, dict[str, Any]], str | None] | None,
    ) -> None:
        get_translator().handle_missing_keys_using(callback)

    @staticmethod
    def get_locale() -> str:
        return get_translator().get_locale()

    @staticmethod
    def set_locale(locale: str) -> None:
        get_translator().set_locale(locale)

    @staticmethod
    def get_fallback() -> str:
        return get_translator().get_fallback()

    @staticmethod
    def set_fallback(locale: str) -> None:
        get_translator().set_fallback(locale)

    @staticmethod
    def locale() -> str:
        return Lang.get_locale()
