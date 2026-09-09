---
title: Controllers
description: Organize request handling into controller classes.
---

A **controller** is a class that answers one or more routes. Instead of putting
every handler inline in `routes/web.py`, group related actions under
`app/http/controllers` so each file stays small and testable.

## Basic controllers

```python
# app/http/controllers/welcome_controller.py
from almasix.http import Controller
from almasix.prism import view


class WelcomeController(Controller):
    async def index(self):
        return view("welcome", {"title": "Almasix"})
```

Wire the action in a route file:

```python
# routes/web.py
Route.get("/", [WelcomeController, "index"])
```

Generate a stub:

```bash
python smith make:controller PostController
```

Nested namespaces work (`python smith make:controller Admin/UserController`) and create `__init__.py` files as needed.

## Dependency injection

Constructor and method dependencies are resolved from the application container:

```python
# app/http/controllers/demo_controller.py
from almasix.config import ConfigRepository
from almasix.http import Controller, Request


class DemoController(Controller):
    def __init__(self, config: ConfigRepository) -> None:
        self.config = config

    async def with_config(self, request: Request) -> dict:
        return {"app": self.config.get("app.name")}
```

Type-hint `Request` or a [`FormRequest`](/validation/) subclass to receive the current request (validated when using FormRequest).

## Single-action style

Prefer one public `index` / `store` / `show` method per intent. Almasix does not require invokable `__call__` controllers — use an explicitly named method on the route.

## Related

- [Routing](/routing/)
- [Requests](/requests/)
- [Validation](/validation/)
- [Views](/views/)
