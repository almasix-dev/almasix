"""Notification channels."""

config = {
    "default": "mail",
    "channels": {
        "mail": {"driver": "mail"},
        "database": {"driver": "database"},
        "broadcast": {"driver": "broadcast"},
        "vonage": {"driver": "vonage"},
        "slack": {"driver": "slack"},
        "log": {"driver": "log"},
        "array": {"driver": "array"},
    },
}
