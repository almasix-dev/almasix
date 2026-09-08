---
title: Directory Structure
description: How an Almasix application is organized on disk.
---

The default Almasix application structure provides a sensible starting point for both small and large applications. Feel free to organize your application however you like — Almasix imposes almost no restrictions — but understanding the conventions will help you navigate quickly.

## The root directory

### The `app` directory

The core of your application lives here: HTTP controllers, middleware, models, policies, and service providers.

Almasix uses **PascalCase** for class names and **snake_case** for Python packages and modules:

| Layer | Convention | Example |
| --- | --- | --- |
| Class | PascalCase | `class Post(Model)`, `PostController` |
| Package directories | lowercase | `app/models/`, `app/http/controllers/` |
| Module files | snake_case | `post.py`, `post_controller.py` |
| Imports | dotted snake_case | `from app.models.post import Post` |

Generators follow the same rules. `smith make:model Post` writes `app/models/post.py` containing `class Post`. Nested namespaces snake-case as well: `Admin/UserController` → `app/http/controllers/admin/user_controller.py`. `smith make:policy PostPolicy --model=Post` writes `app/policies/post_policy.py`.

### The `bootstrap` directory

Contains `app.py`, where you configure the application and register middleware. See [Middleware](/middleware/).

### The `config` directory

All of your application's configuration files live here (`app.py`, `database.py`, `http.py`, and so on). Browse these files to become familiar with the options available to you.

### The `database` directory

Holds your database migrations and seeders. See [Migrations](/database/migrations/) and [Seeding](/database/seeding/).

### The `routes` directory

Route definitions for your application. By convention:

- `routes/web.py` — routes that return HTML
- `routes/api.py` — routes that return JSON
- `routes/console.py` — scheduled tasks (loaded by `smith schedule:run`, not the HTTP kernel)

### The `app/console` directory

Console `Command` classes (`smith make:command …`). See [Smith Console](/console/) and [Task Scheduling](/scheduling/).

### The `lang` directory

Translation catalogs for localization (`lang/en/…`, `lang/en.json`, and so on).

### The `smith` script

The entry point for Almasix's command-line interface. Generate code, run migrations, schedule work, and open Loupe:

```bash
smith make:controller PostController
smith migrate
smith schedule:run
smith loupe
smith serve
```

:::note
Model meta such as `fillable` and `casts` stay as snake_case class attributes so generated models stay readable and consistent with Articulate conventions.
:::
