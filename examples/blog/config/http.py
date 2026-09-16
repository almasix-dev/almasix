"""HTTP kernel defaults — stacks and aliases are registered in bootstrap/app.py."""

config = {
    # Global stack (every route). Prefer Application.configure().with_middleware(...).
    "middleware": [],
    # Named groups referenced from routes/*.py (`web` / `api`).
    "middleware_groups": {
        "web": [],
        "api": [],
    },
    "middleware_aliases": {},
}
