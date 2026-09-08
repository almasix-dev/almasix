"""Broadcasting connections."""

from almasix.config import env

config = {
    # "log" writes broadcasts to the log and sends nothing, which is the
    # right default until you have decided how they reach a browser.
    # "websocket" runs Almasix's own socket server at the path below.
    "default": env("BROADCAST_CONNECTION", "websocket"),
    "connections": {
        "websocket": {
            "driver": "websocket",
            "key": env("BROADCAST_KEY", "almasix"),
            # Signing falls back to APP_KEY when this is unset.
            "secret": env("BROADCAST_SECRET", "progress-demo-secret"),
            "path": env("BROADCAST_PATH", "/broadcasting/socket"),
            # Let browsers send `client-*` events to each other.
            "client_events": bool(env("BROADCAST_CLIENT_EVENTS", True)),
        },
        "pusher": {
            "driver": "pusher",
            "key": env("PUSHER_APP_KEY"),
            "secret": env("PUSHER_APP_SECRET"),
            "app_id": env("PUSHER_APP_ID"),
            "cluster": env("PUSHER_APP_CLUSTER", "mt1"),
            "host": env("PUSHER_HOST"),
            "port": env("PUSHER_PORT"),
            "scheme": env("PUSHER_SCHEME", "https"),
        },
        "redis": {
            "driver": "redis",
            "connection": env("BROADCAST_REDIS_CONNECTION", "default"),
            "prefix": env("BROADCAST_REDIS_PREFIX", ""),
        },
        "log": {"driver": "log"},
        "null": {"driver": "null"},
    },
    # Middleware on /broadcasting/auth. Sessions live in the web group.
    "middleware": ["web"],
}
