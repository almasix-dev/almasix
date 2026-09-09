"""Routing middleware — signature checks and default parameters.

`signed` is the half of signed URLs that runs on the way in: a link whose
signature no longer matches, or whose `expires` has passed, gets a 403 rather
than reaching the handler that would have honored it.
"""

from __future__ import annotations

from typing import Any

from almasix.http.exceptions import HttpException
from almasix.http.middleware import Middleware, NextCall
from almasix.http.request import Request
from almasix.routing.signing import has_valid_signature


class InvalidSignatureException(HttpException):
    """A signed URL that was edited, or one whose deadline has passed.

    403 rather than 404, because the resource is there — this link is not
    allowed to reach it.
    """

    status_code = 403

    def __init__(self, message: str = "Invalid signature.") -> None:
        super().__init__(message)


class ValidateSignature(Middleware):
    """Laravel's `signed` middleware.

    `signed` checks the whole URL, origin included. `signed:relative` checks
    only the path and query, which is what a proxy that rewrites the host
    needs — and what makes the link survive `http` becoming `https`.
    """

    def __init__(self, mode: str | None = None) -> None:
        self.relative = str(mode or "").strip().lower() in {"relative", "1", "true"}

    async def handle(self, request: Request, call_next: NextCall) -> Any:
        url = str(request.url)
        if not has_valid_signature(url, absolute=not self.relative):
            raise InvalidSignatureException()
        return await call_next(request)


class SetUrlDefaults(Middleware):
    """Feed the current request's parameters to `URL::defaults`.

    A localized application prefixing every route with `{locale}` would
    otherwise have to pass the locale at every `route()` call. This copies the
    parameters it is configured for off the current request, so links
    generated during the request keep the locale the request arrived with.

    The values last exactly as long as the request. Many requests are in
    flight at once in an ASGI process, and a French visitor's locale must not
    end up in the links generated for an English one.
    """

    def __init__(self, parameters: str | None = None) -> None:
        self.parameters = [
            name.strip() for name in str(parameters or "locale").split(",") if name.strip()
        ]

    async def handle(self, request: Request, call_next: NextCall) -> Any:
        from almasix.routing.url import pop_defaults, push_defaults

        found = {
            name: request.path_params[name]
            for name in self.parameters
            if name in request.path_params
        }
        if not found:
            return await call_next(request)
        token = push_defaults(found)
        try:
            return await call_next(request)
        finally:
            pop_defaults(token)
