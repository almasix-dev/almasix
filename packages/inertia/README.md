# almasix-inertia

Server-side [Inertia.js](https://inertiajs.com) adapter for Almasix. Use the
**official** `@inertiajs/vue3`, `@inertiajs/react`, or `@inertiajs/svelte`
clients — this package does not fork them. SSR uses Inertia’s Node SSR protocol.

```python
from inertia import Inertia, lazy, defer

def dashboard():
    return Inertia.render("Dashboard", {
        "user": user,
        "stats": lazy(lambda: expensive()),
        "notes": defer(lambda: load_notes()),
    })
```

Root Prism template ships `@inertia` / `@inertiaHead`. Prop helpers: `lazy`,
`optional`, `defer`, `once`, `merge`. Page `url` honors `APP_BASE_PATH`.

**Extract target:** `almasix-dev/inertia` — see `EXTRACT.md`.

Starlight: **Inertia**.