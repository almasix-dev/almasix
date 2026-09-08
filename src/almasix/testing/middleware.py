"""Standing middleware down for a test (Laravel `withoutMiddleware`)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def without_middleware(app: Any, middleware: Sequence[Any] | Any | None = None) -> None:
    """Stop running this middleware — all of it, when given nothing.

    Authentication, CSRF, and throttling are the usual targets: a test about a
    controller should not have to hold a valid token to reach it.
    """
    _kernel(app).skip_middleware(middleware)


def with_middleware(app: Any) -> None:
    """Put every middleware back (Laravel `withMiddleware`)."""
    _kernel(app).restore_middleware()


def _kernel(app: Any) -> Any:
    kernel = getattr(app, "http_kernel", None)
    if kernel is None:
        raise RuntimeError("This application has no HTTP kernel to take middleware from.")
    return kernel
