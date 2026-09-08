"""Laravel-shaped translator."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from almasix.translation.loader import FileLoader
from almasix.translation.locale import (
    get_fallback_locale,
    peek_locale,
    set_fallback_locale,
    set_locale,
)
from almasix.translation.plural import select as select_plural

_PLACEHOLDER_RE = re.compile(r":([A-Za-z][A-Za-z0-9_]*)")


class Translator:
    """Resolves language lines from file/JSON catalogs with fallback."""

    def __init__(
        self,
        loader: FileLoader | None = None,
        *,
        locale: str = "en",
        fallback: str = "en",
    ) -> None:
        self.loader = loader or FileLoader()
        self._locale = locale
        self._fallback = fallback
        self._missing_handler: Callable[[str, str, dict[str, Any]], str | None] | None = None
        # Do not touch the request ContextVar here — leave it unset so
        # SetLocaleMiddleware can negotiate Accept-Language per request.
        set_fallback_locale(fallback)

    # --- locale -------------------------------------------------------------

    def set_locale(self, locale: str) -> None:
        """Set the active locale for this context only (request-scoped)."""
        set_locale(locale)

    def get_locale(self) -> str:
        current = peek_locale()
        return current if current is not None else self._locale

    def set_default_locale(self, locale: str) -> None:
        """Configure the process default used when no request locale is set."""
        self._locale = locale
        if peek_locale() is None:  # pragma: no branch
            set_locale(locale)

    def set_fallback(self, locale: str) -> None:
        self._fallback = locale
        set_fallback_locale(locale)

    def get_fallback(self) -> str:
        return get_fallback_locale() or self._fallback

    # --- loader passthrough -------------------------------------------------

    def add_path(self, path: str | Path) -> None:
        self.loader.add_path(path)

    def add_json_path(self, path: str | Path) -> None:
        self.loader.add_json_path(path)

    def add_namespace(self, namespace: str, hint: str | Path) -> None:
        self.loader.add_namespace(namespace, hint)

    def add_lines(
        self,
        lines: dict[str, Any],
        locale: str,
        namespace: str = "*",
    ) -> None:
        self.loader.add_lines(lines, locale, namespace)

    def handle_missing_keys_using(
        self,
        callback: Callable[[str, str, dict[str, Any]], str | None] | None,
    ) -> None:
        self._missing_handler = callback

    def clear_cache(self) -> None:
        self.loader.clear_cache()

    # --- resolve ------------------------------------------------------------

    def has(self, key: str, locale: str | None = None, *, fallback: bool = True) -> bool:
        locales = [locale or self.get_locale()]
        if fallback:
            fb = self.get_fallback()
            if fb not in locales:
                locales.append(fb)
        for candidate in locales:
            if self._lookup(key, candidate) is not None:
                return True
        return False

    def has_for_locale(self, key: str, locale: str | None = None) -> bool:
        return self.has(key, locale=locale or self.get_locale(), fallback=False)

    def get(
        self,
        key: str,
        replace: Mapping[str, Any] | None = None,
        locale: str | None = None,
        *,
        fallback: bool = True,
    ) -> str | Any:
        replace = dict(replace or {})
        locales = [locale or self.get_locale()]
        if fallback:  # pragma: no branch
            fb = self.get_fallback()
            if fb not in locales:
                locales.append(fb)

        for candidate in locales:
            line = self._lookup(key, candidate)
            if line is not None:
                if isinstance(line, dict):
                    return line
                return self.make_replacements(str(line), replace)

        if self._missing_handler is not None:
            handled = self._missing_handler(key, locales[0], replace)
            if handled is not None:  # pragma: no branch
                return handled
        return key

    def choice(
        self,
        key: str,
        number: float,
        replace: Mapping[str, Any] | None = None,
        locale: str | None = None,
    ) -> str:
        replace = dict(replace or {})
        replace.setdefault("count", number)
        active = locale or self.get_locale()
        line = self.get(key, replace={}, locale=active)
        if not isinstance(line, str):
            line = str(line)
        # If missing, get() returns the key — still run selector for pipes inline.
        selected = select_plural(line, number, active)
        return self.make_replacements(selected, replace)

    # --- placeholders -------------------------------------------------------

    def make_replacements(self, line: str, replace: Mapping[str, Any]) -> str:
        if not replace:
            return line

        # Longest keys first so :name does not eat :names.
        items = sorted(replace.items(), key=lambda item: len(str(item[0])), reverse=True)

        def substitute(match: re.Match[str]) -> str:
            token = match.group(1)
            lower = token.lower()
            for key, value in items:
                if str(key).lower() != lower:
                    continue
                text = "" if value is None else str(value)
                if token.isupper():
                    return text.upper()
                if token[0].isupper() and token[1:].islower():
                    return text[:1].upper() + text[1:] if text else text
                if token[0].isupper():
                    # :NaMe → Title Case each word (Laravel-ish)
                    return text.title()
                return text
            return match.group(0)

        return _PLACEHOLDER_RE.sub(substitute, line)

    # --- internal -----------------------------------------------------------

    def _lookup(self, key: str, locale: str) -> Any | None:
        namespace, group, item = self._parse_key(key)

        # JSON / bare-key path (group "*").
        if group == "*":
            json_lines = self.loader.load_json(locale)
            needle = key if namespace == "*" else (item or key)
            if namespace != "*" and "::" in key:
                needle = key.split("::", 1)[1]
            if needle in json_lines:
                return json_lines[needle]
            # Runtime lines registered under the "*" namespace.
            runtime = self.loader._lines.get((locale, namespace)) or {}
            if needle in runtime:
                return runtime[needle]
            if key in runtime:
                return runtime[key]
            return None

        assert group is not None
        lines = self.loader.load(namespace, group, locale)
        if item is None:
            return lines or None
        return self._dig(lines, item)

    def _parse_key(self, key: str) -> tuple[str, str | None, str | None]:
        namespace = "*"
        remainder = key
        if "::" in key:
            namespace, remainder = key.split("::", 1)

        # JSON keys are often full sentences with periods — treat as JSON when
        # the first segment is not a plausible group file name, handled later.
        if "." not in remainder:
            # Prefer JSON for bare keys; group lookup would need a group name.
            return namespace, "*", remainder

        group, _, item = remainder.partition(".")
        # Heuristic: if group looks like a sentence start (space / uppercase long),
        # treat whole key as JSON. Keep short snake identifiers as groups.
        if " " in group or (len(group) > 32):
            return namespace, "*", key if namespace == "*" else remainder
        return namespace, group, item or None

    @staticmethod
    def _dig(lines: dict[str, Any], item: str) -> Any | None:
        # Prefer nested dicts (`min.string` → lines["min"]["string"]), but also
        # accept a flat key that literally contains dots.
        if item in lines:
            return lines[item]
        current: Any = lines
        for part in item.split("."):
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current
