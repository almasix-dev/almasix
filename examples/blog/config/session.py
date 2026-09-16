"""Session configuration."""

from almasix.config import env

config = {
    "driver": env("SESSION_DRIVER", "cookie"),
    "lifetime": int(env("SESSION_LIFETIME", 120) or 120),
    "cookie": env("SESSION_COOKIE", "almasix_session"),
    "path": env("SESSION_PATH", "/"),
    "secure": env("SESSION_SECURE_COOKIE", False),
    # Database driver (SESSION_DRIVER=database) — `smith session:table` writes
    # the migration when the scaffold's default one has been removed.
    "table": env("SESSION_TABLE", "sessions"),
    # Redis driver (SESSION_DRIVER=redis):
    "connection": env("SESSION_CONNECTION", "default"),
    "prefix": env("SESSION_PREFIX", "almasix_session:"),
}
