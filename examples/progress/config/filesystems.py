"""Filesystem disks."""

from almasix.config import env

config = {
    "default": env("FILESYSTEM_DISK", "local"),
    "cloud": "s3",
    "disks": {
        "local": {
            "driver": "local",
            "root": "storage/app",
            "visibility": "private",
        },
        "public": {
            "driver": "local",
            "root": "storage/app/public",
            "url": "/storage",
            "visibility": "public",
        },
        "memory": {"driver": "memory"},
        "s3": {
            "driver": "s3",
            "key": env("AWS_ACCESS_KEY_ID"),
            "secret": env("AWS_SECRET_ACCESS_KEY"),
            "region": env("AWS_DEFAULT_REGION"),
            "bucket": env("AWS_BUCKET"),
            "url": env("AWS_URL"),
            "endpoint": env("AWS_ENDPOINT"),
            "visibility": "private",
        },
    },
    "links": {
        "public/storage": "storage/app/public",
    },
}
