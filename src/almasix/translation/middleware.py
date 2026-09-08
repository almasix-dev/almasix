"""SetLocale middleware — Accept-Language for api, explicit set always wins."""

from __future__ import annotations

from almasix.http.middleware import Middleware, NextCall
from almasix.http.request import Request
from almasix.translation.helpers import get_translator
from almasix.translation.locale import peek_locale, set_locale


class SetLocaleMiddleware(Middleware):
    """Resolve the request locale: explicit set, then session, then Accept-Language."""

    async def handle(self, request: Request, call_next: NextCall):
        translator = get_translator()
        # Explicit set_locale() earlier in the pipeline wins — do not override.
        if peek_locale() is None:
            session_locale = _session_locale(request)
            if session_locale:
                set_locale(session_locale)
            else:
                header = request.header("accept-language") or request.header("Accept-Language")
                if header:
                    available = _available_locales(translator)
                    chosen = _negotiate(header, available, translator.get_locale())
                    if chosen:  # pragma: no branch
                        set_locale(chosen)
                else:
                    set_locale(translator.get_locale())
        return await call_next(request)


def _session_locale(request: Request) -> str | None:
    session = getattr(request, "_session", None)
    if session is None:
        return None
    value = session.get("locale")
    return str(value) if value else None


def _available_locales(translator) -> list[str]:
    locales: set[str] = {translator.get_locale(), translator.get_fallback()}
    for root in translator.loader._paths:
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if child.is_dir() and child.name != "vendor":
                locales.add(child.name)
            elif child.suffix == ".json":
                locales.add(child.stem)
    return sorted(locales)


def _negotiate(header: str, available: list[str], default: str) -> str | None:
    available_lower = {item.lower(): item for item in available}
    for candidate in _parse_accept_language(header):
        lower = candidate.lower()
        if lower in available_lower:
            return available_lower[lower]
        # en-US → en
        primary = lower.split("-", 1)[0]
        if primary in available_lower:
            return available_lower[primary]
    return default if default else None


def _parse_accept_language(header: str) -> list[str]:
    parts: list[tuple[float, str]] = []
    for item in header.split(","):
        item = item.strip()
        if not item:
            continue
        lang, _, rest = item.partition(";")
        quality = 1.0
        if rest.startswith("q="):
            try:
                quality = float(rest[2:])
            except ValueError:
                quality = 0.0
        parts.append((quality, lang.strip()))
    parts.sort(key=lambda pair: pair[0], reverse=True)
    return [lang for _, lang in parts if lang]
