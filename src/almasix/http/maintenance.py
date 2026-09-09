"""Maintenance mode — the HTTP half of `smith down`.

The marker file is shared with the scheduler: while it exists, scheduled
tasks skip themselves and this middleware answers every request with a 503
(or a redirect, or a rendered template). A secret bypass lets the operator
still reach the application — Laravel's cookie trick, so a link with
`?secret=…` sets a cookie and subsequent requests pass through.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from almasix.http.exceptions import ServiceUnavailableHttpException
from almasix.http.middleware import Middleware
from almasix.http.request import Request
from almasix.http.response import make_response

#: Cookie Laravel sets once the secret query parameter has been accepted.
BYPASS_COOKIE = "almasix_maintenance"


class PreventRequestsDuringMaintenance(Middleware):
    """Answer 503 while `storage/framework/down` exists.

    Requests carrying the bypass cookie, or hitting a URI in
    `except`, pass through. A `?secret=` query that matches the marker's
    secret is redirected to the same URL without the query and with the
    cookie set — so the operator does not have to keep pasting the secret.
    """

    def __init__(self, except_: list[str] | None = None) -> None:
        self.except_ = list(except_ or [])

    async def handle(self, request: Request, call_next: Any) -> Any:
        payload = maintenance_payload(request)
        if payload is None:
            return await call_next(request)
        if self._is_excepted(request):
            return await call_next(request)

        secret = str(payload.get("secret") or "")
        if secret and _has_bypass(request, secret):
            return await call_next(request)

        if secret and request.query("secret") == secret:
            return _grant_bypass(request, secret)

        return _deny(request, payload)

    def _is_excepted(self, request: Request) -> bool:
        path = request.path
        return any(path == uri or path.startswith(uri.rstrip("*")) for uri in self.except_)


def maintenance_payload(request: Request | None = None) -> dict[str, Any] | None:
    """The decoded `down` marker, or `None` when the application is live."""
    path = _marker_path(request)
    if path is None or not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # The M31 marker was the word "down". Treat it as an empty payload so
        # an application taken down before this middleware existed still
        # answers 503 rather than 500.
        return {}
    return dict(data) if isinstance(data, Mapping) else {}


def write_marker(
    base_path: Path,
    *,
    secret: str | None = None,
    redirect: str | None = None,
    retry: int | None = None,
    refresh: int | None = None,
    status: int = 503,
    template: str | None = None,
    render: str | None = None,
) -> Path:
    """Write the marker `smith down` leaves for the HTTP kernel to read."""
    path = base_path / "storage" / "framework" / "down"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "except": [],
        "status": int(status),
    }
    if secret:
        payload["secret"] = secret
    if redirect:
        payload["redirect"] = redirect
    if retry is not None:
        payload["retry"] = int(retry)
    if refresh is not None:
        payload["refresh"] = int(refresh)
    if template:
        payload["template"] = template
    if render:
        payload["render"] = render
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def clear_marker(base_path: Path) -> None:
    (base_path / "storage" / "framework" / "down").unlink(missing_ok=True)


def _marker_path(request: Request | None) -> Path | None:
    from almasix.framework.helpers import current_application

    application = current_application()
    if application is None:
        return None
    return Path(application.base_path) / "storage" / "framework" / "down"


def _has_bypass(request: Request, secret: str) -> bool:
    cookie = request.cookie(BYPASS_COOKIE)
    return bool(cookie) and cookie == secret


def _grant_bypass(request: Request, secret: str) -> Any:
    """Redirect to the same URL without `?secret=`, carrying the bypass cookie."""
    from almasix.http.response import Redirect

    target = str(request.url).split("?", 1)[0]
    response = Redirect(target, status_code=302)
    response.set_cookie(BYPASS_COOKIE, secret, path="/", httponly=True, samesite="lax")
    return response


def _deny(request: Request, payload: Mapping[str, Any]) -> Any:
    status = int(payload.get("status") or 503)
    retry = payload.get("retry")
    redirect = payload.get("redirect")
    if redirect:
        from almasix.http.response import Redirect

        response = Redirect(str(redirect), status_code=302)
        if retry is not None:
            response.headers["Retry-After"] = str(int(retry))
        return response

    body = _rendered_body(payload) or "Service Unavailable"
    headers: dict[str, str] = {}
    if retry is not None:
        headers["Retry-After"] = str(int(retry))
    refresh = payload.get("refresh")
    if refresh is not None:
        headers["Refresh"] = str(int(refresh))

    # Prefer a rendered Prism view when one was named; otherwise a plain 503.
    if payload.get("render") or payload.get("template"):
        return make_response(body, status=status, headers=headers)

    raise ServiceUnavailableHttpException(str(body), headers=headers)


def _rendered_body(payload: Mapping[str, Any]) -> str | None:
    view_name = payload.get("render") or payload.get("template")
    if not view_name:
        return None
    try:
        from almasix.framework.helpers import app as current_app
        from almasix.prism.engine import Engine

        engine = current_app().make(Engine)
        return engine.render(str(view_name), {"retry": payload.get("retry")})
    except Exception:
        return None
