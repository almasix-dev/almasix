"""config/signet.py — first-party SPA domains and token expiration."""

from almasix.config import env
from almasix.signet import Signet

config = {
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
    "expiration": env("SIGNET_EXPIRATION", None),
    "token_prefix": env("SIGNET_TOKEN_PREFIX", ""),
}
