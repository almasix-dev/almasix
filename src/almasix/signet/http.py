"""HTTP endpoints shipped by Signet."""

from __future__ import annotations

from starlette.responses import Response

from almasix.session.csrf import csrf_token
from almasix.session.helpers import cookie


async def csrf_cookie() -> Response:
    """``GET /signet/csrf-cookie`` — mint the CSRF / XSRF cookies for SPA login."""
    token = csrf_token()
    if token:
        # SPA clients read XSRF-TOKEN and send it back as X-XSRF-TOKEN.
        cookie().queue("XSRF-TOKEN", token, minutes=60 * 24 * 365 * 2, http_only=False)
    return Response(status_code=204)
