"""Search — which engine finds your models."""

from almasix.config import env

config = {
    # "database" searches the posts table itself, which needs nothing
    # installed — the right default for a demo and for most applications.
    "driver": env("SCOUT_DRIVER", "database"),
    "prefix": env("SCOUT_PREFIX", ""),
    "queue": bool(env("SCOUT_QUEUE", False)),
    "after_commit": False,
    "chunk": {"searchable": 500, "unsearchable": 500},
    "soft_delete": False,
    "identify": bool(env("SCOUT_IDENTIFY", False)),
    "meilisearch": {
        "host": env("MEILISEARCH_HOST", "http://localhost:7700"),
        "key": env("MEILISEARCH_KEY"),
        "index-settings": {
            "posts": {
                "filterableAttributes": ["user_id"],
                "sortableAttributes": ["id"],
            },
        },
    },
}
