"""Session configuration."""

from almasix.config import env

config = {
    "driver": env("SESSION_DRIVER", "cookie"),
    "lifetime": int(env("SESSION_LIFETIME", 120) or 120),
    "cookie": env("SESSION_COOKIE", "almasix_session"),
    "path": env("SESSION_PATH", "/"),
    "secure": env("SESSION_SECURE_COOKIE", False),
    "connection": env("SESSION_CONNECTION", "default"),
    "prefix": env("SESSION_PREFIX", "almasix_session:"),
}
