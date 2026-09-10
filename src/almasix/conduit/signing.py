"""Signed Conduit update URLs — every ``POST /conduit/update`` must carry a valid HMAC.

Unlike Livewire, Almasix signs the update endpoint itself (Laravel ``signed`` /
``signed:relative``). The browser never posts to a bare unsigned path.

Subpath rule: the signature covers the **internal** path (``/conduit/update``),
which is what the mounted ASGI app sees. The public URL prefixes ``APP_BASE_PATH``
only for the browser.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from almasix.config import config
from almasix.routing.signing import expiry_from, has_valid_signature, sign


def _cfg(key: str, default: Any = None) -> Any:
    try:
        value = config(key, default)
    except RuntimeError:
        return default
    return default if value is None else value


def update_path() -> str:
    """Internal route path (no ``APP_BASE_PATH``)."""
    path = str(_cfg("conduit.endpoint", "/conduit/update") or "/conduit/update")
    if not path.startswith("/"):
        path = f"/{path}"
    return path.split("?", 1)[0]


def signature_ttl_minutes() -> float:
    return float(_cfg("conduit.signature_ttl_minutes", 720) or 720)


def sign_update_url(*, minutes: float | None = None) -> str:
    """Return a relatively signed internal update URL (path + query only)."""
    ttl = signature_ttl_minutes() if minutes is None else float(minutes)
    expires = expiry_from(minutes=ttl)
    return sign(update_path(), expires_at=expires, absolute=False)


def public_signed_update_url(*, minutes: float | None = None) -> str:
    """Browser-facing signed URL, including ``APP_BASE_PATH`` when set."""
    from almasix.routing.url import UrlGenerator

    signed_internal = sign_update_url(minutes=minutes)
    parts = urlsplit(signed_internal)
    gen = UrlGenerator.from_config()
    # Prefix path with base; keep signed query intact.
    prefixed = gen.to(parts.path, absolute=False)
    if parts.query:
        return f"{prefixed}?{parts.query}"
    return prefixed


def verify_update_request_url(url: str) -> bool:
    """Whether ``url`` (absolute or path+query) carries a valid relative signature."""
    parts = urlsplit(url)
    # Prefer path+query — matches what the mounted app receives.
    relative = urlunsplit_path_query(parts.path, parts.query)
    return has_valid_signature(relative, absolute=False)


def urlunsplit_path_query(path: str, query: str) -> str:
    if query:
        return f"{path}?{query}"
    return path or "/"
