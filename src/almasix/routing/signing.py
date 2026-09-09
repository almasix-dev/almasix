"""Signed URLs — a link nobody can edit without invalidating it.

Laravel's `URL::signedRoute` appends a `signature` query parameter that is an
HMAC of the rest of the URL under `APP_KEY`. Change any part of the link and
the signature no longer matches, so a "cancel my subscription" mail can carry
the subscription id in the open.

Two shapes, both Laravel's:

* **Absolute.** The signature covers scheme, host, path, and query. This is
  what `signed_route` produces, and it cannot be replayed against another host.
* **Relative.** The signature covers the path and query only, so the link
  survives a proxy that rewrites the origin. `has_valid_relative_signature`
  is the one to check it with.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import SplitResult, parse_qsl, urlencode, urlsplit, urlunsplit

#: The query parameters the signature itself lives in.
SIGNATURE_KEY = "signature"
EXPIRES_KEY = "expires"


class InvalidSignature(RuntimeError):
    """A signed URL that was edited, or that has expired."""


def app_key_bytes() -> bytes:
    """The signing key, tolerating the `base64:` prefix `key:generate` writes."""
    from almasix.config import config

    try:
        key = str(config("app.key", "") or "")
    except RuntimeError:
        # No application booted: a script signing a URL has no configuration
        # to read, and a fixed development key is better than a crash.
        key = ""
    key = key or "almasix-dev-key"
    key = key.removeprefix("base64:")
    return key.encode("utf-8")


def signature_for(url: str) -> str:
    """The HMAC of ``url`` with the signature parameter removed."""
    return hmac.new(app_key_bytes(), url.encode("utf-8"), hashlib.sha256).hexdigest()


def sign(url: str, *, expires_at: int | None = None, absolute: bool = True) -> str:
    """Append `expires` (when given) and `signature` to ``url``."""
    parts = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parts.query) if key != SIGNATURE_KEY]
    query = [(key, value) for key, value in query if key != EXPIRES_KEY]
    if expires_at is not None:
        query.append((EXPIRES_KEY, str(int(expires_at))))
    payload = _payload(parts, query, absolute=absolute)
    query.append((SIGNATURE_KEY, signature_for(payload)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def has_valid_signature(url: str, *, absolute: bool = True, ignore_expiry: bool = False) -> bool:
    """Whether ``url`` still carries the signature it was signed with."""
    parts = urlsplit(url)
    pairs = parse_qsl(parts.query)
    provided = ""
    kept: list[tuple[str, str]] = []
    expires: str | None = None
    for key, value in pairs:
        if key == SIGNATURE_KEY:
            provided = value
            continue
        if key == EXPIRES_KEY:
            expires = value
        kept.append((key, value))
    if not provided:
        return False
    if not ignore_expiry and expires is not None and _has_expired(expires):
        return False
    expected = signature_for(_payload(parts, kept, absolute=absolute))
    return hmac.compare_digest(expected, provided)


def has_valid_relative_signature(url: str, *, ignore_expiry: bool = False) -> bool:
    """`has_valid_signature` for a link signed without its origin."""
    return has_valid_signature(url, absolute=False, ignore_expiry=ignore_expiry)


def expiry_from(minutes: float | None = None, *, seconds: float | None = None) -> int:
    """A Unix timestamp ``minutes`` (or ``seconds``) from now."""
    delta = float(seconds) if seconds is not None else float(minutes or 0) * 60
    return int(time.time() + delta)


def _payload(parts: SplitResult, query: list[tuple[str, str]], *, absolute: bool) -> str:
    """What the HMAC is taken over: the URL with `signature` removed.

    Query parameters are sorted, because a mail client that reorders them —
    or a router that rebuilds the query — must not invalidate the link.
    """
    ordered = urlencode(sorted(query))
    path = parts.path or "/"
    if absolute:
        return urlunsplit((parts.scheme, parts.netloc, path, ordered, ""))
    return urlunsplit(("", "", path, ordered, ""))


def _has_expired(expires: str) -> bool:
    try:
        return int(expires) < int(time.time())
    except (TypeError, ValueError):
        # An `expires` nobody can read is not a deadline that has passed; the
        # signature check below will reject the edit anyway.
        return False


def signature_parameters(query: Mapping[str, Any] | None) -> dict[str, Any]:
    """``query`` without the two parameters signing owns."""
    return {
        key: value
        for key, value in (query or {}).items()
        if key not in {SIGNATURE_KEY, EXPIRES_KEY}
    }
