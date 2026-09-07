"""Base controller."""

from __future__ import annotations

from avalon.auth.access.requests import AuthorizesRequests


class Controller(AuthorizesRequests):
    """Base class for HTTP controllers (async action methods)."""
