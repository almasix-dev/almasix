"""Scaffold a new Almasix application tree."""

from __future__ import annotations

import re
from pathlib import Path

_APP_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


class ScaffoldError(ValueError):
    """Invalid scaffold request."""


def validate_app_name(name: str) -> str:
    if not _APP_NAME_RE.match(name):
        raise ScaffoldError(
            f"Invalid app name {name!r}. Use letters, numbers, underscores, or hyphens; "
            "must start with a letter."
        )
    return name


def title_case(name: str) -> str:
    parts = re.split(r"[-_]+", name)
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def scaffold_app(name: str, destination: Path | None = None) -> Path:
    """Create a new Almasix application directory and return its path."""
    name = validate_app_name(name)
    root = (destination or Path.cwd() / name).resolve()
    if root.exists() and any(root.iterdir()):
        raise ScaffoldError(f"Directory already exists and is not empty: {root}")

    root.mkdir(parents=True, exist_ok=True)
    display = title_case(name)

    files: dict[str, str] = {
        "smith": _SMITH_SCRIPT,
        "README.md": _readme(name, display),
        "pyproject.toml": _pyproject(name, display),
        ".env": _env_file(display),
        ".env.example": _env_file(display),
        ".gitignore": _GITIGNORE,
        "app/__init__.py": "",
        "app/http/__init__.py": "",
        "app/http/controllers/__init__.py": "",
        "app/http/controllers/welcome_controller.py": _welcome_controller(),
        "app/http/controllers/health_controller.py": _health_controller(),
        "app/providers/__init__.py": "",
        "app/providers/app_service_provider.py": _app_service_provider(),
        "bootstrap/__init__.py": "",
        "bootstrap/app.py": _bootstrap_app(),
        "config/__init__.py": "",
        "config/app.py": _config_app(display),
        "config/http.py": _config_http(),
        "config/session.py": _config_session(),
        "config/auth.py": _config_auth(),
        "config/hashing.py": _config_hashing(),
        "config/database.py": _config_database(),
        "config/logging.py": _config_logging(),
        "config/filesystems.py": _config_filesystems(),
        "config/queue.py": _config_queue(),
        "config/mail.py": _config_mail(),
        "config/notifications.py": _config_notifications(),
        "config/cache.py": _config_cache(),
        "config/concurrency.py": _config_concurrency(),
        "config/broadcasting.py": _config_broadcasting(),
        "config/scout.py": _config_scout(),
        "config/redis.py": _config_redis(),
        "config/loupe.py": _config_loupe(),
        "app/models/__init__.py": "",
        "app/console/__init__.py": "",
        "app/console/commands/__init__.py": "",
        "app/exceptions/__init__.py": "",
        "app/exceptions/handler.py": _exception_handler(),
        "tests/__init__.py": "",
        "tests/conftest.py": _tests_conftest(),
        "tests/feature/__init__.py": "",
        "tests/feature/example_test.py": _tests_feature_example(),
        "tests/unit/__init__.py": "",
        "tests/unit/example_test.py": _tests_unit_example(),
        "database/__init__.py": "",
        "database/migrations/.gitkeep": "",
        "database/seeders/__init__.py": "",
        "database/seeders/database_seeder.py": _database_seeder(),
        "routes/__init__.py": "",
        "routes/api.py": _routes_api(),
        "routes/web.py": _routes_web(),
        "routes/console.py": _routes_console(),
        "routes/channels.py": _routes_channels(),
        "lang/en/messages.py": _lang_messages_en(),
        "lang/en/validation.py": _lang_validation_stub(),
        "lang/en.json": '{}\n',
        "resources/views/.gitkeep": "",
        "resources/views/mail/.gitkeep": "",
        "resources/views/errors/404.prism.html": _error_view(404, "Not Found"),
        "resources/views/errors/419.prism.html": _error_view(419, "Page Expired"),
        "resources/views/errors/429.prism.html": _error_view(429, "Too Many Requests"),
        "resources/views/errors/500.prism.html": _error_view(500, "Server Error"),
        "resources/views/errors/503.prism.html": _error_view(503, "Service Unavailable"),
        "resources/css/app.css": _resources_css(),
        "resources/js/app.js": _resources_js(),
        "package.json": _package_json(name),
        "vite.config.js": _vite_config(),
        "storage/app/.gitkeep": "",
        "storage/app/public/.gitkeep": "",
        "storage/framework/.gitkeep": "",
        "storage/framework/cache/data/.gitkeep": "",
        "storage/logs/.gitkeep": "",
        "public/.gitkeep": "",
        "public/build/.gitkeep": "",
    }

    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if relative == "smith":
            path.chmod(path.stat().st_mode | 0o111)

    return root


_SMITH_SCRIPT = '''#!/usr/bin/env python
"""Smith — Almasix in-application CLI.

Once this project is installed into its virtualenv (``pip install -e .``):

    smith version
    smith serve
    smith list
    smith loupe   # aliases: tinker, repl

Or via this root script, which needs no install step:

    python smith serve
"""

from __future__ import annotations

from almasix.smith.cli import app

if __name__ == "__main__":
    app()
'''

_GITIGNORE = """__pycache__/
*.py[cod]
.venv/
venv/
.env
.pytest_cache/
.ruff_cache/
.mypy_cache/
.prism_cache/
node_modules/
public/build/
!public/build/.gitkeep
storage/framework/views/
storage/framework/schedule/
database/*.sqlite
database/*.sqlite-*
*.egg-info/
dist/
build/
"""


def _env_file(display: str) -> str:
    return f"""APP_NAME={display}
APP_ENV=local
APP_DEBUG=true
APP_URL=http://127.0.0.1:3000
# Public path prefix when hosted under a subpath, e.g. /apps/{display.lower()}
APP_BASE_PATH=
APP_KEY=base64:local-dev-key-change-me
# Comma-separated previous keys for graceful rotation (optional)
# APP_PREVIOUS_KEYS=
APP_LOCALE=en
APP_FALLBACK_LOCALE=en
DB_CONNECTION=sqlite
DB_DATABASE=database/database.sqlite
CACHE_STORE=file
CACHE_PREFIX=almasix_cache_
REDIS_CLIENT=default
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
# REDIS_URL=redis://127.0.0.1:6379/0
SESSION_DRIVER=cookie
"""


def _readme(name: str, display: str) -> str:
    return f"""# {display}

Almasix application generated with `almasix new {name}`.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
smith serve
```

Open http://127.0.0.1:3000

With the venv active, run `smith …` directly. `python smith …` also works via the root script.

## Frontend (Vite + Tailwind)

```bash
npm install
npm run dev      # Vite HMR during development
npm run build    # emit into public/build
```

Create more apps with `almasix new`.
"""


def _package_json(name: str) -> str:
    return f"""{{
  "name": "{name}",
  "private": true,
  "type": "module",
  "scripts": {{
    "dev": "vite",
    "build": "vite build"
  }},
  "devDependencies": {{
    "@tailwindcss/vite": "^4.0.0",
    "tailwindcss": "^4.0.0",
    "vite": "^6.0.0"
  }}
}}
"""


def _vite_config() -> str:
    return """import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";
import { resolve } from "node:path";

export default defineConfig({
  plugins: [tailwindcss()],
  build: {
    outDir: "public/build",
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: {
        app: resolve("resources/js/app.js"),
        css: resolve("resources/css/app.css"),
      },
    },
  },
  server: {
    origin: "http://127.0.0.1:5173",
  },
});
"""


def _resources_css() -> str:
    return """@import "tailwindcss";
"""


def _resources_js() -> str:
    return """import "../css/app.css";

console.log("Almasix app.js ready");
"""

def _pyproject(name: str, display: str) -> str:
    return f"""[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{name}"
version = "0.1.0"
description = "{display} — Almasix application"
requires-python = ">=3.11"
dependencies = [
    "almasix",
]

# Smith drives this application, so it belongs to this project's environment
# rather than to a global Almasix install.
[project.scripts]
smith = "almasix.smith.cli:app"

[project.optional-dependencies]
dev = [
    "pytest",
    "pytest-asyncio",
]

[tool.hatch.build.targets.wheel]
packages = ["app", "bootstrap", "config", "routes"]

[tool.pytest.ini_options]
# ``smith test`` runs this. Async tests need no decorator, and a test class may
# be named either ``TestPost`` or ``PostTest`` — ``smith make:test`` writes the
# second, the way Laravel does.
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["."]
python_files = ["test_*.py", "*_test.py"]
python_classes = ["Test*", "*Test"]

[tool.pylint.basic]
# Model meta (`fillable`, `casts`) is snake_case by design, not UPPER_CASE.
class-attribute-rgx = "([a-z_][a-z0-9_]*|[A-Z_][A-Z0-9_]*)$"
attr-rgx = "([a-z_][a-z0-9_]*|[A-Z_][A-Z0-9_]*)$"
"""


def _tests_conftest() -> str:
    return '''"""Shared test setup — one application, and fakes that clean up."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from almasix.testing import restore_fakes


@pytest.fixture(autouse=True)
def _no_fake_outlives_its_test() -> Iterator[None]:
    """A faked mailer or queue must not still be installed for the next test."""
    yield
    restore_fakes()
'''


def _tests_feature_example() -> str:
    return '''"""The application answers, end to end."""

from __future__ import annotations

from almasix.testing import TestCase


class ExampleTest(TestCase):
    """A feature test drives real routes through the real middleware."""

    async def test_the_home_page_answers(self) -> None:
        response = await self.get("/")

        response.assert_ok()

    async def test_the_health_endpoint_reports_ok(self) -> None:
        response = await self.get_json("/api/health")

        response.assert_ok().assert_json({"status": "ok"})
'''


def _tests_unit_example() -> str:
    return '''"""A unit test — no application, no database, no HTTP."""

from __future__ import annotations

from almasix.support import Str


class ExampleTest:
    def test_a_slug_is_a_slug(self) -> None:
        assert Str.slug("Hello There") == "hello-there"
'''


def _bootstrap_app() -> str:
    return '''"""Application entry — boots the Almasix kernel and exposes ASGI."""

from __future__ import annotations

from pathlib import Path

from almasix.framework import Application, Middleware
from almasix.translation import SetLocaleMiddleware

BASE_PATH = Path(__file__).resolve().parent.parent


def configure_middleware(middleware: Middleware) -> None:
    """Register HTTP middleware (Laravel ``bootstrap/app.php`` shape)."""
    # Behind a load balancer / ingress (from almasix.http import HEADER_X_FORWARDED_ALL):
    # middleware.trust_proxies(at="*", headers=HEADER_X_FORWARDED_ALL)
    # middleware.trust_hosts(at=["example.com", "*.example.com"])
    from almasix.auth import (
        Authenticate,
        AuthenticateWithBasicAuth,
        Authorize,
        EnsureEmailIsVerified,
        RedirectIfAuthenticated,
        RequirePassword,
    )
    from almasix.auth.middleware import StartAuth
    from almasix.session import EncryptCookies, StartSession, VerifyCsrfToken

    middleware.alias(
        {
            "locale": SetLocaleMiddleware,
            "cookies.encrypt": EncryptCookies,
            "session.start": StartSession,
            "csrf": VerifyCsrfToken,
            "auth.start": StartAuth,
            "auth": Authenticate,
            "guest": RedirectIfAuthenticated,
            "password.confirm": RequirePassword,
            "auth.basic": AuthenticateWithBasicAuth,
            "verified": EnsureEmailIsVerified,
            "can": Authorize,
        }
    )
    middleware.web(
        prepend=["cookies.encrypt", "session.start", "csrf", "auth.start"],
        append=["locale"],
    )
    middleware.api(prepend=["auth.start"], append=["locale"])


application = (
    Application.configure(BASE_PATH)
    .with_middleware(configure_middleware)
    .create()
)
asgi = application.asgi
'''


def _config_app(display: str) -> str:
    return f'''"""Application configuration."""

from almasix.config import env

config = {{
    "name": env("APP_NAME", "{display}"),
    "env": env("APP_ENV", "local"),
    "debug": env("APP_DEBUG", True),
    "url": env("APP_URL", "http://127.0.0.1:3000"),
    "base_path": env("APP_BASE_PATH", ""),
    "key": env("APP_KEY", "base64:local-dev-key-change-me"),
    "previous_keys": env("APP_PREVIOUS_KEYS", ""),
    "locale": env("APP_LOCALE", "en"),
    "fallback_locale": env("APP_FALLBACK_LOCALE", "en"),
    "providers": [
        "app.providers.app_service_provider.AppServiceProvider",
    ],
}}
'''


def _config_session() -> str:
    return '''"""Session configuration."""

from almasix.config import env

config = {
    "driver": env("SESSION_DRIVER", "cookie"),
    "lifetime": int(env("SESSION_LIFETIME", 120) or 120),
    "cookie": env("SESSION_COOKIE", "almasix_session"),
    "path": env("SESSION_PATH", "/"),
    "secure": env("SESSION_SECURE_COOKIE", False),
    # Redis driver (SESSION_DRIVER=redis):
    "connection": env("SESSION_CONNECTION", "default"),
    "prefix": env("SESSION_PREFIX", "almasix_session:"),
}
'''


def _config_auth() -> str:
    return '''"""Authentication defaults — guards, providers, password brokers."""

from almasix.config import env

config = {
    "defaults": {
        "guard": env("AUTH_GUARD", "web"),
        "passwords": env("AUTH_PASSWORD_BROKER", "users"),
    },
    "guards": {
        "web": {
            "driver": "session",
            "provider": "users",
        },
        "api": {
            "driver": "token",
            "provider": "users",
            "input_key": "api_token",
            "storage_key": "api_token",
        },
    },
    "providers": {
        "users": {
            "driver": "articulate",
            "model": "app.models.user.User",
        },
    },
    "passwords": {
        "users": {
            "provider": "users",
            "table": "password_reset_tokens",
            "expire": 60,
            "throttle": 60,
        },
    },
    "password_timeout": 10800,
}
'''


def _config_hashing() -> str:
    return '''"""Password hashing configuration."""

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
'''


def _config_database() -> str:
    return '''"""Database connections."""

from almasix.config import env

config = {
    "default": env("DB_CONNECTION", "sqlite"),
    "connections": {
        "sqlite": {
            "driver": "sqlite",
            "database": env("DB_DATABASE", "database/database.sqlite"),
        },
        "pgsql": {
            "driver": "pgsql",
            "host": env("DB_HOST", "127.0.0.1"),
            "port": env("DB_PORT", 5432),
            "database": env("DB_DATABASE", "almasix"),
            "username": env("DB_USERNAME", "almasix"),
            "password": env("DB_PASSWORD", ""),
        },
        "mysql": {
            "driver": "mysql",
            "host": env("DB_HOST", "127.0.0.1"),
            "port": env("DB_PORT", 3306),
            "database": env("DB_DATABASE", "almasix"),
            "username": env("DB_USERNAME", "almasix"),
            "password": env("DB_PASSWORD", ""),
        },
        "mariadb": {
            "driver": "mariadb",
            "host": env("DB_HOST", "127.0.0.1"),
            "port": env("DB_PORT", 3306),
            "database": env("DB_DATABASE", "almasix"),
            "username": env("DB_USERNAME", "almasix"),
            "password": env("DB_PASSWORD", ""),
        },
        "sqlsrv": {
            "driver": "sqlsrv",
            "host": env("DB_HOST", "127.0.0.1"),
            "port": env("DB_PORT", 1433),
            "database": env("DB_DATABASE", "almasix"),
            "username": env("DB_USERNAME", "sa"),
            "password": env("DB_PASSWORD", ""),
            "odbc_driver": env("DB_ODBC_DRIVER", "ODBC Driver 18 for SQL Server"),
            "trust_server_certificate": env("DB_TRUST_SERVER_CERTIFICATE", "yes"),
        },
        # Optional — not first-party in Laravel (community niche like yajra/laravel-oci8).
        "oracle": {
            "driver": "oracle",
            "host": env("DB_HOST", "127.0.0.1"),
            "port": env("DB_PORT", 1521),
            "service_name": env("DB_SERVICE_NAME", env("DB_DATABASE", "ORCL")),
            "username": env("DB_USERNAME", "almasix"),
            "password": env("DB_PASSWORD", ""),
        },
        # Document stores. Articulate reaches these through Document models;
        # "memory" keeps documents in the process, which is what tests want.
        "mongodb": {
            "driver": "mongodb",
            "dsn": env("MONGODB_DSN", ""),
            "host": env("MONGODB_HOST", "127.0.0.1"),
            "port": env("MONGODB_PORT", 27017),
            "database": env("MONGODB_DATABASE", "almasix"),
            "username": env("MONGODB_USERNAME", ""),
            "password": env("MONGODB_PASSWORD", ""),
        },
        "memory": {
            "driver": "memory",
        },
    },
}
'''


def _config_logging() -> str:
    return '''"""Logging channels."""

from almasix.config import env

config = {
    "default": env("LOG_CHANNEL", "stack"),
    "channels": {
        "stack": {
            "driver": "stack",
            "channels": ["single"],
            "ignore_exceptions": False,
        },
        "single": {
            "driver": "single",
            "path": "storage/logs/almasix.log",
            "level": env("LOG_LEVEL", "debug"),
        },
        "daily": {
            "driver": "daily",
            "path": "storage/logs/almasix.log",
            "level": env("LOG_LEVEL", "debug"),
            "days": 14,
        },
        "stderr": {
            "driver": "stderr",
            "level": env("LOG_LEVEL", "debug"),
        },
        "null": {
            "driver": "null",
        },
    },
}
'''


def _config_filesystems() -> str:
    return '''"""Filesystem disks."""

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
'''


def _config_queue() -> str:
    return '''"""Queue connections."""

from almasix.config import env

config = {
    "default": env("QUEUE_CONNECTION", "sync"),
    "connections": {
        "sync": {"driver": "sync"},
        "database": {
            "driver": "database",
            "table": "jobs",
            "queue": "default",
            "retry_after": 90,
        },
        "redis": {
            "driver": "redis",
            "connection": env("REDIS_QUEUE_CONNECTION", "default"),
            "queue": "queues",
        },
    },
    "failed": {
        "driver": "database",
        "connection": env("DB_CONNECTION", "sqlite"),
        "table": "failed_jobs",
    },
}
'''


def _config_mail() -> str:
    return '''"""Mailers and from address."""

from almasix.config import env

config = {
    "default": env("MAIL_MAILER", "log"),
    "from": {
        "address": env("MAIL_FROM_ADDRESS", "hello@example.com"),
        "name": env("MAIL_FROM_NAME", "Example"),
    },
    "mailers": {
        "smtp": {
            "transport": "smtp",
            "host": env("MAIL_HOST", "127.0.0.1"),
            "port": env("MAIL_PORT", 2525),
            "encryption": env("MAIL_ENCRYPTION"),
            "username": env("MAIL_USERNAME"),
            "password": env("MAIL_PASSWORD"),
        },
        "log": {"transport": "log"},
        "array": {"transport": "array"},
    },
}
'''


def _config_notifications() -> str:
    return '''"""Notification channels."""

config = {
    "default": "mail",
    "channels": {
        "mail": {"driver": "mail"},
        "database": {"driver": "database"},
        "log": {"driver": "log"},
        "array": {"driver": "array"},
    },
}
'''


def _config_loupe() -> str:
    return '''"""Loupe — what the REPL has waiting for you (`smith loupe`).

Your models under app/models are aliased automatically; everything here is
for the rest.
"""

config = {
    # Commands to have as callables in the shell: "inspire" → inspire().
    "commands": [],
    # Extra names to import, as name -> dotted path.
    "alias": {
        # "Str": "almasix.support.Str",
    },
    # Names to keep out of the shell, even if a model would have claimed them.
    "dont_alias": [],
}
'''


def _config_cache() -> str:
    return '''"""Cache stores."""

from almasix.config import env

config = {
    "default": env("CACHE_STORE", "file"),
    "prefix": env("CACHE_PREFIX", "almasix_cache_"),
    "stores": {
        "array": {"driver": "array"},
        "file": {
            "driver": "file",
            "path": "storage/framework/cache/data",
        },
        "database": {
            "driver": "database",
            "connection": None,
            "table": "cache",
            "lock_table": "cache_locks",
        },
        "redis": {
            "driver": "redis",
            "connection": env("REDIS_CACHE_CONNECTION", "default"),
        },
        "null": {"driver": "null"},
    },
}
'''


def _config_concurrency() -> str:
    return '''"""Concurrency drivers."""

from almasix.config import env

config = {
    # "thread" runs any callable and suits I/O-bound work; "fork" gives real
    # parallelism on Unix; "process" needs picklable tasks; "sync" is serial.
    "default": env("CONCURRENCY_DRIVER", "thread"),
    "drivers": {
        "thread": {
            "driver": "thread",
            "max_workers": int(env("CONCURRENCY_MAX_WORKERS", 16) or 16),
        },
        "fork": {"driver": "fork"},
        "process": {"driver": "process"},
        "sync": {"driver": "sync"},
    },
}
'''


def _config_broadcasting() -> str:
    return '''"""Broadcasting connections."""

from almasix.config import env

config = {
    # "log" writes broadcasts to the log and sends nothing, which is the
    # right default until you have decided how they reach a browser.
    # "websocket" runs Almasix's own socket server at the path below.
    "default": env("BROADCAST_CONNECTION", "log"),
    "connections": {
        "websocket": {
            "driver": "websocket",
            "key": env("BROADCAST_KEY", "almasix"),
            # Signing falls back to APP_KEY when this is unset.
            "secret": env("BROADCAST_SECRET"),
            "path": env("BROADCAST_PATH", "/broadcasting/socket"),
            # Let browsers send `client-*` events to each other.
            "client_events": bool(env("BROADCAST_CLIENT_EVENTS", False)),
        },
        "pusher": {
            "driver": "pusher",
            "key": env("PUSHER_APP_KEY"),
            "secret": env("PUSHER_APP_SECRET"),
            "app_id": env("PUSHER_APP_ID"),
            "cluster": env("PUSHER_APP_CLUSTER", "mt1"),
            "host": env("PUSHER_HOST"),
            "port": env("PUSHER_PORT"),
            "scheme": env("PUSHER_SCHEME", "https"),
        },
        "redis": {
            "driver": "redis",
            "connection": env("BROADCAST_REDIS_CONNECTION", "default"),
            "prefix": env("BROADCAST_REDIS_PREFIX", ""),
        },
        "log": {"driver": "log"},
        "null": {"driver": "null"},
    },
    # Middleware on /broadcasting/auth. Sessions live in the web group.
    "middleware": ["web"],
}
'''


def _config_scout() -> str:
    return '''"""Search — which engine finds your models."""

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
'''


def _routes_channels() -> str:
    return '''"""Broadcast channels — who may listen to what."""

from almasix.broadcasting import Broadcast


@Broadcast.channel("users.{user_id}")
def user_channel(user, user_id):
    """A user may listen to their own channel, and nobody else's."""
    return str(user.get_key()) == str(user_id)
'''


def _config_redis() -> str:
    return '''"""Redis connections."""

from almasix.config import env

config = {
    "default": env("REDIS_CLIENT", "default"),
    "connections": {
        "default": {
            "url": env("REDIS_URL"),
            "host": env("REDIS_HOST", "127.0.0.1"),
            "port": int(env("REDIS_PORT", 6379) or 6379),
            "database": int(env("REDIS_DB", 0) or 0),
            "password": env("REDIS_PASSWORD"),
            "username": env("REDIS_USERNAME"),
        },
    },
}
'''


def _exception_handler() -> str:
    return '''"""Application exception handler."""

from __future__ import annotations

from almasix.exceptions import Handler as ExceptionHandler


class Handler(ExceptionHandler):
    """Customize report/render hooks here."""

    dont_report: list[type[BaseException]] = []
'''


def _error_view(status: int, message: str) -> str:
    del status, message  # templates receive runtime values from the Handler
    return '''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{{ status }} — {{ message }}</title>
  <style>
    :root { color-scheme: light dark; }
    body { margin: 0; min-height: 100vh; display: grid; place-items: center;
           font: 16px/1.5 system-ui, sans-serif; background: #f6f7f9; color: #1a1d23; }
    main { text-align: center; padding: 2rem; }
    h1 { margin: 0 0 .5rem; font-size: 3.5rem; letter-spacing: -.04em; }
    p { margin: 0; color: #5b6575; }
  </style>
</head>
<body>
  <main>
    <h1>{{ status }}</h1>
    <p>{{ message }}</p>
  </main>
</body>
</html>
'''


def _config_http() -> str:
    return '''"""HTTP kernel defaults — stacks and aliases are registered in bootstrap/app.py."""

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
'''


def _lang_messages_en() -> str:
    return '''"""Application messages."""

translations = {
    "welcome": "Welcome to Almasix",
}
'''


def _database_seeder() -> str:
    return '''"""DatabaseSeeder — entry point for `python smith db:seed` / `migrate --seed`."""

from __future__ import annotations

from almasix.orm import Seeder


class DatabaseSeeder(Seeder):
    """DatabaseSeeder."""

    async def run(self) -> None:
        """Seed the application's database."""
        # await self.call([UserSeeder])
'''


def _lang_validation_stub() -> str:
    return '''"""Override framework validation messages here (optional).

Publish the full set with `python smith lang:publish`.
"""

translations = {}
'''


def _app_service_provider() -> str:
    return '''"""Application service provider."""

from __future__ import annotations

from almasix.providers import ServiceProvider


class AppServiceProvider(ServiceProvider):
    """Application service provider."""

    def register(self) -> None:
        """Bind application services into the container."""

    def boot(self) -> None:
        """Bootstrap application services."""
'''


def _welcome_controller() -> str:
    return '''"""Welcome controller — web routes return HTML."""

from __future__ import annotations

from almasix.config import config
from almasix.http import Controller, Response, html
from almasix.routing import url


class WelcomeController(Controller):
    """Welcome page — HTML entry for web routes."""

    async def index(self) -> Response:
        name = str(config("app.name", "Almasix"))
        # url() keeps links correct when the app is hosted under APP_BASE_PATH.
        health = url("/api/health", absolute=False)
        return html(
            f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{name}</title>
</head>
<body>
  <h1>Welcome to Almasix</h1>
  <p>{name} is running.</p>
  <p>Web routes render HTML; API routes return JSON — try <a href="{health}">{health}</a>.</p>
</body>
</html>"""
        )
'''


def _health_controller() -> str:
    return '''"""Health controller — API routes return JSON."""

from __future__ import annotations

from almasix.config import config
from almasix.http import Controller


class HealthController(Controller):
    """Health check — JSON status for API routes."""

    async def index(self) -> dict[str, str]:
        return {
            "status": "ok",
            "app": str(config("app.name", "Almasix")),
            "env": str(config("app.env", "local")),
        }
'''


def _routes_web() -> str:
    return '''"""Web routes — browser facing, stateful, HTML responses."""

from app.http.controllers.welcome_controller import WelcomeController
from almasix.routing import Route

with Route.group(middleware=["web"]):
    Route.get("/", [WelcomeController, "index"])
'''


def _routes_api() -> str:
    return '''"""API routes — stateless, JSON responses."""

from app.http.controllers.health_controller import HealthController
from almasix.routing import Route

with Route.group(prefix="/api", middleware=["api"]):
    Route.get("/health", [HealthController, "index"])
'''


def _routes_console() -> str:
    return '''"""Console schedule — loaded by ``python smith schedule:run``."""

from __future__ import annotations

from almasix.console import schedule

# schedule.call(lambda: None, description="heartbeat").every_minute()
# schedule.command("inspire").hourly()
'''
