"""Application configuration."""

from __future__ import annotations

import sys
from pathlib import Path

from almasix.config import env

# In-repo packages (Courier M29, Inertia M55). Conduit lives in ``almasix.conduit``.
_PACKAGES = Path(__file__).resolve().parents[3] / "packages"
for _pkg in ("courier", "inertia"):
    _src = _PACKAGES / _pkg / "src"
    if _src.is_dir() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))

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
        "courier.provider.CourierServiceProvider",
        "inertia.provider.InertiaServiceProvider",
    ],
    "skip_provider_discovery": False,
    "dont_discover": [],
}
