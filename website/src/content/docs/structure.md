---
title: Directory Structure
description: How an Almasix application is organized on disk.
---

A new Almasix application follows a small set of conventions so you always
know where controllers, routes, config, and templates live. You can reorganize
freely — Almasix does not require this layout — but the scaffold is a sensible
default for small and large apps alike.

## The root directory

A typical app from `almasix new` looks like this:

```text title="blog/"
blog/
  app/
  bootstrap/
  config/
  database/
  lang/
  public/
  resources/
  routes/
  storage/
  tests/
  pyproject.toml
  smith
```

### The `app` directory

Application code lives here: HTTP controllers, models, policies, console
commands, and service providers.

Almasix uses **PascalCase** for class names and **snake_case** for Python
packages and modules:

| Layer | Convention | Example |
| --- | --- | --- |
| Class | PascalCase | `class Post(Model)`, `PostController` |
| Package directories | lowercase | `app/models/`, `app/http/controllers/` |
| Module files | snake_case | `post.py`, `post_controller.py` |
| Imports | dotted snake_case | `from app.models.post import Post` |

Generators follow the same rules. `smith make:model Post` writes
`app/models/post.py` containing `class Post`. Nested namespaces snake-case as
well: `Admin/UserController` → `app/http/controllers/admin/user_controller.py`.
`smith make:policy PostPolicy --model=Post` writes `app/policies/post_policy.py`.

Common subfolders:

| Path | Role |
| --- | --- |
| `app/http/controllers/` | Route handlers (see [Controllers](/controllers/)) |
| `app/models/` | Articulate models |
| `app/providers/` | Service providers that register bindings and boot hooks |
| `app/console/commands/` | Smith `Command` classes |
| `app/exceptions/` | Exception handler and custom exceptions |

### The `bootstrap` directory

Contains `app.py`, where you configure the application and register middleware.
The ASGI entry point exported here (`asgi`) is what Uvicorn serves. See
[Middleware](/middleware/).

### The `config` directory

All of your application's configuration files live here (`app.py`,
`database.py`, `http.py`, `session.py`, and so on). Browse these files to see
the options available to you. Values usually read from `.env`.

### The `database` directory

Holds migrations, seeders, and model factories:

| Path | Role |
| --- | --- |
| `database/migrations/` | Schema changes |
| `database/seeders/` | Sample or required data |
| `database/factories/` | Fake models for tests and demos |

See [Migrations](/database/migrations/) and [Seeding](/database/seeding/).

### The `routes` directory

Route definitions for your application. By convention:

- `routes/web.py` — browser routes (HTML, sessions, CSRF)
- `routes/api.py` — JSON / client routes (stateless by default)
- `routes/console.py` — scheduled tasks (loaded by `smith schedule:run`, not the HTTP kernel)
- `routes/channels.py` — broadcasting channel authorization (when used)

See [Routing](/routing/).

### The `resources` directory

Front-end sources and **Prism** templates (`.prism.html`):

| Path | Role |
| --- | --- |
| `resources/views/` | Server-rendered templates |
| `resources/css/` | Stylesheets for Vite stacks |
| `resources/js/` | JavaScript entry points (and SPA pages when using Inertia) |

See [Views](/views/) and [Asset Bundling](/asset-bundling/).

### The `public` directory

Files the web server may serve directly. Vite writes hashed assets into
`public/build/`. Put static files you want at a stable URL here (favicons,
robots.txt, and so on).

### The `storage` directory

Writable runtime data: logs, framework cache, and uploaded files under
`storage/app/`. Keep this out of version control except for `.gitkeep` placeholders.

### The `lang` directory

Translation catalogs for localization (`lang/en/…`, `lang/en.json`, and so on).

### The `tests` directory

pytest suite when you scaffolded tests. Feature tests live under
`tests/feature/`; unit tests under `tests/unit/`. Run with `python smith test`.

### The `smith` script

The entry point for Almasix's command-line interface. Generate code, run
migrations, schedule work, and open Loupe:

```bash title="terminal"
python smith make:controller PostController
python smith migrate
python smith schedule:run
python smith loupe
python smith serve
```

:::note
Model meta such as `fillable` and `casts` stay as snake_case class attributes
so generated models stay readable and consistent with Articulate conventions.
:::

## Next steps

- [Routing](/routing/) — map URLs to controllers
- [Controllers](/controllers/) — organize handlers
- [Views](/views/) — render Prism templates
