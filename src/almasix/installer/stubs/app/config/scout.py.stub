"""Search — which engine finds your models."""

from almasix.config import env

config = {
    # "database" searches the tables you already have, and needs nothing
    # installed. "collection" filters rows in Python, "meilisearch" talks to
    # a real index, and "null" finds nothing.
    "driver": env("SCOUT_DRIVER", "database"),
    # Prepended to every index name: one search service, several apps.
    "prefix": env("SCOUT_PREFIX", ""),
    # True, or {"connection": ..., "queue": ...}, to index on the queue.
    "queue": bool(env("SCOUT_QUEUE", False)),
    # Wait for the surrounding transaction before touching the index.
    "after_commit": False,
    "chunk": {"searchable": 500, "unsearchable": 500},
    # Keep trashed rows in the index behind a `__soft_deleted` flag.
    "soft_delete": False,
    "identify": bool(env("SCOUT_IDENTIFY", False)),
    "meilisearch": {
        "host": env("MEILISEARCH_HOST", "http://localhost:7700"),
        "key": env("MEILISEARCH_KEY"),
        # Per-index settings, pushed by `smith scout:sync-index-settings`:
        # "posts": {"filterableAttributes": ["author_id"]},
        "index-settings": {},
    },
}
