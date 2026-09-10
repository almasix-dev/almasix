---
title: Package Development
description: Build first-party and third-party packages that extend Almasix like Laravel packages do.
---

## Introduction

Packages are how first-party and community code plugs into Almasix: a
`ServiceProvider` registers bindings, merges config, loads routes / views /
translations / migrations, offers publishable assets, and optionally registers
console commands. The progress app's in-repo **Courier** package
(`packages/courier`) is the living example — run `smith progress:packages` to
see it boot, publish tags, resolve `courier::welcome`, and hit `/courier`.

```bash
smith make:package courier
pip install -e packages/courier
smith vendor:publish --tag=courier-config
```

## Service providers

Every package ships a provider that subclasses
`almasix.providers.ServiceProvider`. Call the helpers from `register()` (config
and bindings) and `boot()` (routes, views, publishes, commands):

```python
from pathlib import Path
from almasix.providers import ServiceProvider

_HERE = Path(__file__).resolve().parent


class CourierServiceProvider(ServiceProvider):
    def register(self) -> None:
        self.merge_config_from(_HERE / "config" / "courier.py", "courier")

    def boot(self) -> None:
        self.publishes(
            {_HERE / "config" / "courier.py": self.app.path("config", "courier.py")},
            "courier-config",
        )
        self.load_routes_from(_HERE / "routes" / "web.py")
        self.load_views_from(_HERE / "resources" / "views", "courier")
        self.load_translations_from(_HERE / "lang", "courier")
        self.load_migrations_from(_HERE / "database" / "migrations")
        self.publishes_migrations(
            {
                _HERE / "database" / "migrations" / "0001_01_01_000000_create_courier_messages_table.py": (
                    "database/migrations/create_courier_messages_table.py"
                ),
            },
            "courier-migrations",
        )
        self.commands([CourierStatusCommand])
```

Register the provider in the application's `config/app.py` `providers` list,
or rely on [auto-discovery](#package-discovery) via entry points.

## Package discovery

Installed packages advertise providers with the **`almasix.providers`**
entry-point group:

```toml
[project.entry-points."almasix.providers"]
courier = "courier.provider:CourierServiceProvider"
```

On boot, `Application.register_configured_providers` registers:

1. `FoundationServiceProvider`
2. Every path in `config/app.py` → `providers`
3. Every discovered entry point **unless** discovery is disabled

### Configuring discovery

```python
# config/app.py
config = {
    "providers": [
        "app.providers.app_service_provider.AppServiceProvider",
    ],
    # Skip entry-point discovery entirely.
    "skip_provider_discovery": False,
    # Distribution names to exclude (Laravel ``dont-discover``).
    "dont_discover": ["almasix-spam"],
}
```

`PackageManifest` resolves entry points through `importlib.metadata`. A broken
optional package is skipped softly so one bad install cannot take down boot.

## Resources

### Configuration — `merge_config_from`

Loads a Python config module (`config = {...}` or top-level names) under a key.
Package defaults fill missing keys; values already in the application win
(published config overrides package defaults):

```python
self.merge_config_from(_HERE / "config" / "courier.py", "courier")
# config("courier.driver")
```

### Routes — `load_routes_from`

Executes a route file through `Application.load_route_file` — the same path
broadcasting uses for `routes/channels.py`:

```python
self.load_routes_from(_HERE / "routes" / "web.py")
```

### Views — `load_views_from`

Registers a Prism namespace so `view("courier::welcome")` resolves against the
package tree. Published overrides live under
`resources/views/vendor/courier/` and win over the package hint. The helper
also declares a `{namespace}-views` publish tag for the whole views directory.

```python
self.load_views_from(_HERE / "resources" / "views", "courier")
from almasix.prism.helpers import render
render("courier::welcome", {"driver": "pigeon"})
```

### Migrations — `load_migrations_from` / `publishes_migrations`

`load_migrations_from` registers directories with the migrator so
`smith migrate` finds package migrations **without** publishing them.

`publishes_migrations` is like `publishes`, but `vendor:publish` rewrites each
destination filename with a fresh `YYYY_MM_DD_HHMMSS_` prefix so published
migrations sort after the application's existing ones.

### Translations — `load_translations_from`

Registers a language namespace. Catalog files live under
`{path}/{locale}/{group}.py`; keys use `namespace::group.key`:

```python
self.load_translations_from(_HERE / "lang", "courier")
__("courier::messages.greeting")
```

### Commands — `commands`

Registers `Command` subclasses on the console kernel when it is bound
(providers' `boot()` runs after the kernel is available during Smith boots):

```python
self.commands([CourierStatusCommand])
```

## Publishing assets

`publishes` / `publishes_migrations` only **declare** paths. Users copy them
with:

```bash
smith vendor:publish --tag=courier-config
smith vendor:publish --provider=courier.provider.CourierServiceProvider
smith vendor:publish --all
```

Convention for tags: `{package}-config`, `{package}-migrations`,
`{package}-views`, `{package}-lang`. See [Smith Console](/console/) for the
full `vendor:publish` surface.

## Naming

| Kind | Convention |
| --- | --- |
| First-party Almasix packages | Python: `almasix.*` (Signet, Prism, …). JS clients: `@almasix/*` (Sonar). |
| Third-party / community | Own distribution name (`almasix-courier`, `acme-billing`); **do not** claim the `almasix.` import namespace. |
| Config / publish tags | Package short name: `courier`, `courier-config`. |
| View / lang namespaces | Same short name: `courier::welcome`, `courier::messages.greeting`. |

## Scaffolding — `smith make:package`

```bash
smith make:package courier
smith make:package acme-billing --path=packages/billing
```

Creates under `packages/{name}/` (or `--path`):

- `pyproject.toml` with an `almasix.providers` entry point
- `src/{module}/provider.py` with sample `merge_config_from` / `load_*` / `publishes` calls
- Config, routes, views, lang, and migration stubs
- A README with install and publish notes

## Testing packages

- Unit-test the provider by constructing it with an `Application(tmp_path)`,
  calling `register()` / `boot()`, and asserting config, routes, view
  resolution, and publish tags (`ServiceProvider.forget_publishes()` between
  tests).
- Smoke the living example: `smith progress:packages` and
  `tests/smoke/test_m29_smoke.py`.
- Prefer `almasix.testing.TestCase` / `boot_application()` when the package
  needs a full app boot — see [Testing](/testing/).

## File map

| Piece | Path |
| --- | --- |
| Base provider | `src/almasix/providers/provider.py` |
| Discovery | `src/almasix/providers/package_manifest.py` |
| View namespaces | `src/almasix/prism/engine.py` — `add_namespace` / `::` finder |
| Migration paths | `src/almasix/orm/migration.py` — `register_migration_paths` |
| Generator | `smith make:package` → `almasix.smith.make.make_package` |
| Example package | `packages/courier/` |
| Progress demo | `smith progress:packages` |
