"""Map framework/domain exceptions to HTTP status codes."""

from __future__ import annotations

from almasix.http.exceptions import HttpException

# Statuses with dedicated production templates.
ERROR_STATUSES = (404, 419, 429, 500, 503)

# Lazy-resolved type → status. Keep import-light to avoid cycles at module load.
_STATUS_MAP: list[tuple[str, int]] = [
    ("almasix.orm.builder.ModelNotFoundError", 404),
    ("almasix.prism.engine.ViewNotFoundError", 404),
    ("almasix.support.collection.ItemNotFoundError", 404),
    ("almasix.session.csrf.TokenMismatchError", 419),
]
_RUNTIME_MAP: dict[type[BaseException], int] = {}


def _load_type(dotted: str) -> type[BaseException] | None:
    module_path, _, name = dotted.rpartition(".")
    if not module_path:
        return None
    try:
        module = __import__(module_path, fromlist=[name])
        candidate = getattr(module, name, None)
    except Exception:
        return None
    if isinstance(candidate, type) and issubclass(candidate, BaseException):
        return candidate
    return None


def resolved_status_map() -> dict[type[BaseException], int]:
    """Return the live mapping (types that import successfully)."""
    mapping: dict[type[BaseException], int] = dict(_RUNTIME_MAP)
    for dotted, status in _STATUS_MAP:
        cls = _load_type(dotted)
        if cls is not None:
            mapping[cls] = status
    return mapping


def status_for_exception(exc: BaseException) -> int:
    """Resolve an HTTP status for ``exc`` (HttpException wins, then the map, else 500)."""
    if isinstance(exc, HttpException):
        return int(exc.status_code)
    for cls, status in resolved_status_map().items():
        if isinstance(exc, cls):
            return int(status)
    return 500


def register_status(exc_type: type[BaseException], status: int) -> None:
    """Extend the map at runtime (tests / app boot hooks)."""
    _RUNTIME_MAP[exc_type] = int(status)


# Default production copy keys (lang/en/errors.py).
STATUS_MESSAGE_KEYS: dict[int, str] = {
    404: "errors.not_found",
    419: "errors.page_expired",
    429: "errors.too_many_requests",
    500: "errors.server_error",
    503: "errors.service_unavailable",
}


def default_message_for_status(status: int) -> str:
    """Translated default message for a production error page / JSON body."""
    key = STATUS_MESSAGE_KEYS.get(status, "errors.server_error")
    try:
        from almasix.translation import __

        return __(key)
    except Exception:
        fallbacks = {
            404: "Not Found",
            419: "Page Expired",
            429: "Too Many Requests",
            500: "Server Error",
            503: "Service Unavailable",
        }
        return fallbacks.get(status, "Server Error")


def polarity_from_path(path: str, *, api_prefix: str = "/api") -> str:
    """Infer polarity for unmatched / ASGI-level errors from the request path.

    Paths under the API prefix use JSON; everything else uses HTML. This is a
    path convention for *unmatched* routes only — registered routes still use
    middleware-group polarity (``web`` / ``api``).
    """
    normalized = path or "/"
    prefix = (api_prefix or "/api").rstrip("/") or "/api"
    if normalized == prefix or normalized.startswith(prefix + "/"):
        return "api"
    return "web"
