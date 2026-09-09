"""Password hashing configuration."""

from almasix.config import env

config = {
    "driver": env("HASH_DRIVER", "bcrypt"),
    "bcrypt": {
        "rounds": int(env("BCRYPT_ROUNDS", 12) or 12),
    },
    "argon2": {
        "memory": int(env("ARGON_MEMORY", 65536) or 65536),
        "threads": int(env("ARGON_THREADS", 1) or 1),
        "time": int(env("ARGON_TIME", 4) or 4),
    },
    "rehash_on_login": True,
}
