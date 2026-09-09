"""Security headers — the ones a browser enforces without the application knowing.

Every response should say what it is willing to be embedded in, how referrers
travel, and whether a script the page did not mint may run. Laravel ships that
as a package; Almasix ships it as middleware that is on by default for the web
stack, because a scaffold that forgets the headers is worse than one that
opts out of them.
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping, Sequence
from typing import Any

from almasix.http.middleware import Middleware
from almasix.http.request import Request

#: Where the CSP nonce for this request lives on the request.
CSP_NONCE_ATTR = "csp_nonce"

#: Sensible defaults. An application that wants less can empty a value; one
#: that wants more overrides via the middleware constructor or `config/http.py`.
DEFAULT_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-XSS-Protection": "0",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class SecurityHeaders(Middleware):
    """Attach the security headers to every response that leaves the stack.

    CSP is the one that needs help from the application: a `nonce-…` source
    only works when the same nonce is written onto every trusted `<script>` /
    `<style>` tag. Call `csp_nonce()` (or read `request.csp_nonce`) from the
    template to get it.
    """

    def __init__(
        self,
        *,
        headers: Mapping[str, str] | None = None,
        csp: str | None = None,
        hsts: str | bool | None = None,
        remove: Sequence[str] | None = None,
    ) -> None:
        self.headers = dict(DEFAULT_HEADERS)
        if headers:
            self.headers.update({str(k): str(v) for k, v in headers.items()})
        for name in remove or ():
            self.headers.pop(str(name), None)
        self.csp = csp
        # `True` means the common production value; a string is used as-is;
        # `False` / `None` leaves HSTS off (the right default for local HTTP).
        if hsts is True:
            self.hsts = "max-age=31536000; includeSubDomains"
        elif hsts is False or hsts is None:
            self.hsts = None
        else:
            self.hsts = str(hsts)

    async def handle(self, request: Request, call_next: Any) -> Any:
        nonce = secrets.token_urlsafe(16)
        setattr(request, CSP_NONCE_ATTR, nonce)
        response = await call_next(request)
        for name, value in self.headers.items():
            if value:
                response.headers.setdefault(name, value)
        if self.csp:
            response.headers.setdefault(
                "Content-Security-Policy", self.csp.replace("{nonce}", nonce)
            )
        if self.hsts and _is_https(request):
            response.headers.setdefault("Strict-Transport-Security", self.hsts)
        return response


def csp_nonce(request: Request | None = None) -> str:
    """The CSP nonce for this request, or `""` outside one.

    Prefer this over reading the attribute: a template rendered from a queue
    job has no request, and an empty string is a safer answer than a crash.
    """
    if request is None:
        from almasix.http.request import get_request

        request = get_request()
    if request is None:
        return ""
    return str(getattr(request, CSP_NONCE_ATTR, "") or "")


def _is_https(request: Request) -> bool:
    url = str(request.url)
    return url.startswith("https://") or request.header("x-forwarded-proto") == "https"
