"""Signet façade — model override, stateful domains, test helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from urllib.parse import urlparse

from almasix.signet.transient_token import TransientToken


class Signet:
    """Laravel Sanctum-class façade."""

    _personal_access_token_model: type | None = None
    _acting_as_user: Any | None = None
    _acting_as_guard: str | None = None

    @classmethod
    def personal_access_token_model(cls) -> type:
        if cls._personal_access_token_model is not None:
            return cls._personal_access_token_model
        from almasix.signet.personal_access_token import PersonalAccessToken

        return PersonalAccessToken

    @classmethod
    def use_personal_access_token_model(cls, model: type) -> None:
        cls._personal_access_token_model = model

    @classmethod
    def current_application_url_with_port(cls) -> str:
        """Host (+ port) from ``APP_URL`` for the ``stateful`` domain list."""
        try:
            from almasix.config import config, env

            raw = str(env("APP_URL", "") or config("app.url", "") or "")
        except Exception:  # pragma: no cover
            raw = ""
        if not raw:
            return "localhost"
        parsed = urlparse(raw if "://" in raw else f"http://{raw}")
        host = parsed.hostname or "localhost"
        if parsed.port:
            return f"{host}:{parsed.port}"
        return host

    @classmethod
    def current_request_host(cls) -> str:
        """Placeholder replaced at runtime with the request host."""
        return "__almasix_signet_current_request_host__"

    @classmethod
    def acting_as(
        cls,
        user: Any,
        abilities: Sequence[str] | None = None,
        *,
        guard: str = "signet",
    ) -> Any:
        """Authenticate ``user`` for the next request (tests)."""
        if hasattr(user, "with_access_token"):
            user.with_access_token(TransientToken(abilities))
        cls._acting_as_user = user
        cls._acting_as_guard = guard
        return user

    @classmethod
    def clear_acting_as(cls) -> None:
        cls._acting_as_user = None
        cls._acting_as_guard = None

    @classmethod
    def take_acting_as(cls) -> tuple[Any | None, str | None]:
        user, guard = cls._acting_as_user, cls._acting_as_guard
        cls.clear_acting_as()
        return user, guard


def stateful_domains() -> list[str]:
    """Configured first-party SPA domains (with helper placeholders expanded)."""
    try:
        from almasix.config import config

        raw = list(config("signet.stateful", []) or [])
    except Exception:  # pragma: no cover
        raw = []
    domains: list[str] = []
    for item in raw:
        text = str(item).strip()
        if not text:
            continue
        if text == Signet.current_request_host():
            continue  # expanded per-request in ``is_from_frontend``
        if text == "__app_url__":
            domains.append(Signet.current_application_url_with_port())
            continue
        domains.append(text)
    # Always include APP_URL host when not listed.
    app_host = Signet.current_application_url_with_port()
    if app_host and app_host not in domains:
        domains.append(app_host)
    return domains


def is_from_frontend(request: Any) -> bool:
    """Whether the request Origin/Referer matches a stateful domain."""
    domains = stateful_domains()
    # Runtime placeholder: same host as the request is always stateful.
    try:
        host = request.headers.get("host") or ""
    except Exception:  # pragma: no cover
        host = ""
    if host:
        domains = [*domains, host.split(",")[0].strip()]

    origin = ""
    try:
        origin = request.headers.get("origin") or ""
        if not origin:
            referer = request.headers.get("referer") or request.headers.get("referrer") or ""
            if referer:
                origin = referer
    except Exception:  # pragma: no cover
        return False

    if not origin:
        # Same-origin browser navigations may omit Origin; treat Host match + cookie as SPA.
        return False

    parsed = urlparse(origin)
    candidate = parsed.netloc or parsed.path
    if not candidate:
        return False
    candidate = candidate.lower()
    for domain in domains:
        normalized = domain.lower().lstrip(".")
        if candidate == normalized or candidate.endswith("." + normalized):
            return True
    return False
