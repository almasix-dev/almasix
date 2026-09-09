"""Default ``config/signet.py`` values when the app has not published the file."""

from __future__ import annotations

from typing import Any

from almasix.signet.signet import Signet


def default_signet_config() -> dict[str, Any]:
    return {
        "stateful": [
            Signet.current_application_url_with_port(),
            "localhost",
            "localhost:3000",
            "127.0.0.1",
            "127.0.0.1:8000",
            "::1",
            Signet.current_request_host(),
        ],
        "guard": ["web"],
        "expiration": None,
        "token_prefix": "",
    }
