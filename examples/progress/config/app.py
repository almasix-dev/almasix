"""Application configuration."""

from __future__ import annotations

import sys
from pathlib import Path

from almasix.config import env

# In-repo Courier package (M29). Smith boots via config without importing
# ``bootstrap.app``, so the path must be available here.
_COURIER_SRC = Path(__file__).resolve().parents[3] / "packages" / "courier" / "src"
if _COURIER_SRC.is_dir() and str(_COURIER_SRC) not in sys.path:
    sys.path.insert(0, str(_COURIER_SRC))

config = {
    "name": env("APP_NAME", "Progress"),
    "env": env("APP_ENV", "local"),
    "debug": env("APP_DEBUG", True),
    "url": env("APP_URL", "http://127.0.0.1:3000"),
    "base_path": env("APP_BASE_PATH", ""),
    "key": env("APP_KEY", "base64:progress-local-dev-key-change-me"),
    "previous_keys": env("APP_PREVIOUS_KEYS", ""),
    "locale": env("APP_LOCALE", "en"),
    "fallback_locale": env("APP_FALLBACK_LOCALE", "en"),
    "providers": [
        "app.providers.app_service_provider.AppServiceProvider",
        # In-repo M29 demo package (also discoverable via almasix.providers).
        "courier.provider.CourierServiceProvider",
    ],
    # Package auto-discovery (entry points group ``almasix.providers``).
    "skip_provider_discovery": False,
    # Distribution names to skip, e.g. ["almasix-courier"].
    "dont_discover": [],
}
