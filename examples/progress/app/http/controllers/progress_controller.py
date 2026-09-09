"""Milestone board — HTML on the web route, JSON on the API route."""

from __future__ import annotations

from almasix import __version__
from almasix.config import config
from almasix.http import Controller, Response
from almasix.prism import view
from almasix.routing import url


def _milestones() -> list[dict]:
    # Keep in sync with docs/PLAN.md as milestones land.
    return [
        {
            "id": "M0",
            "name": "Skeleton",
            "status": "complete",
            "proof": ["almasix new", "python smith serve", "examples/progress scaffold"],
        },
        {
            "id": "M1",
            "name": "Application kernel",
            "status": "complete",
            "proof": [
                "bootstrap Application",
                f"config app.name={config('app.name')}",
                "FoundationServiceProvider + AppServiceProvider",
            ],
        },
        {
            "id": "M2",
            "name": "HTTP + routing",
            "status": "complete",
            "proof": [
                "Route DSL + nested groups/prefix",
                "controllers via container DI",
                "middleware groups (web/api) + aliases",
                "Request all/input/query/post/only/except_/files",
                "web HTML vs api JSON polarity",
                "HttpException JSON",
                "application.asgi",
            ],
        },
        {
            "id": "M3",
            "name": "Validation + DX",
            "status": "complete",
            "proof": [
                "FormRequest + Laravel-shaped 422",
                "authorize() -> 403, messages(), attributes()",
                "python smith make:controller/middleware/provider/request",
                "url() honoring APP_BASE_PATH",
            ],
        },
        {
            "id": "M4",
            "name": "Localization",
            "status": "complete",
            "proof": [
                "lang/ PHP+JSON catalogs",
                "__() / trans_choice() + CLDR plurals",
                "namespaces + lang:publish / missing",
                "Number helpers + SetLocale",
            ],
        },
        {
            "id": "M5",
            "name": "Articulate ORM",
            "status": "complete",
            "proof": [
                "GET /api/orm feature tour",
                "eager load / soft deletes / pivot / morphs",
                "smith migrate / make:model",
                "query builder exhausted in M42, schema and pagination in M43",
            ],
        },
        {
            "id": "M6",
            "name": "Prism",
            "status": "complete",
            "proof": [
                ".prism.html layouts + @foreach",
                "components / slots / @props",
                "@push / @stack / @parent",
                "view() + @csrf / @auth / @guest",
            ],
        },
        {
            "id": "M7",
            "name": "Auth",
            "status": "complete",
            "proof": [
                "cookie session + CSRF + EncryptCookies",
                "session + token guards / remember-me",
                "Hash (bcrypt + optional argon2id)",
                "Password broker + auth middleware",
                "GET /login · /api/me",
            ],
        },
        {
            "id": "M8",
            "name": "Error handling",
            "status": "complete",
            "proof": [
                "Handler report/render",
                "APP_DEBUG page vs production views",
                "errors:publish + log channels",
                "GET /boom · /api/explode",
            ],
        },
        {
            "id": "M9",
            "name": "Console + scheduler",
            "status": "complete",
            "proof": [
                "Command base + smith list",
                "schedule:run / schedule:work",
                "smith loupe REPL",
                "Almasix Prompts + dump()/dd()",
                "progress:hello · progress:prompts",
            ],
        },
        {
            "id": "M10",
            "name": "Filesystem",
            "status": "complete",
            "proof": ["Storage disks", "local + memory + S3", "storage:link"],
        },
        {
            "id": "M11",
            "name": "Queues + workers",
            "status": "complete",
            "proof": ["Job dispatch", "queue:work", "failed jobs", "progress:demo"],
        },
        {
            "id": "M12",
            "name": "Mail",
            "status": "complete",
            "proof": ["Mailable + Mailer", "log/array/SMTP", "Markdown mail"],
        },
        {
            "id": "M13",
            "name": "Notifications",
            "status": "complete",
            "proof": ["Notifiable", "mail + database channels", "email verification"],
        },
        {
            "id": "M14",
            "name": "Helpers + Strings",
            "status": "complete",
            "proof": [
                "Arr / Number / data_* helpers",
                "Str / Stringable / str_()",
                "smith progress:helpers",
            ],
        },
        {
            "id": "M15",
            "name": "Cache",
            "status": "complete",
            "proof": [
                "Cache / cache() façade",
                "array + file + database stores",
                "atomic locks · array tags",
                "progress:cache",
            ],
        },
        {
            "id": "M16",
            "name": "Redis",
            "status": "complete",
            "proof": [
                "Redis / redis() façade",
                "cache + session + queue drivers",
                "progress:redis",
            ],
        },
        {
            "id": "M17",
            "name": "Encryption",
            "status": "complete",
            "proof": [
                "Crypt façade",
                "JSON-safe encrypt + previous keys",
                "progress:encryption",
            ],
        },
        {
            "id": "M18",
            "name": "Events",
            "status": "complete",
            "proof": [
                "dispatch / listen / subscribe",
                "queued listeners",
                "progress:events",
            ],
        },
        {
            "id": "M19",
            "name": "Authorization",
            "status": "complete",
            "proof": [
                "Gate / Policy / Authorizable",
                "@can / @cannot / can middleware",
                "progress:authorization",
            ],
        },
        {
            "id": "M20",
            "name": "HTTP Client",
            "status": "complete",
            "proof": [
                "Http.get/post façade",
                "fakes / retry / pool",
                "progress:http",
            ],
        },
        {
            "id": "M21",
            "name": "Processes",
            "status": "complete",
            "proof": [
                "Process.run / start / pool / pipe",
                "timeouts, streaming, fakes, assertions",
                "progress:process",
            ],
        },
        {
            "id": "M22",
            "name": "Concurrency",
            "status": "complete",
            "proof": [
                "Concurrency.run / defer / arun",
                "thread / fork / process / sync drivers",
                "progress:concurrency",
            ],
        },
        {
            "id": "M23",
            "name": "API Resources",
            "status": "complete",
            "proof": [
                "JsonResource / ResourceCollection",
                "conditionals, wrapping, pagination meta",
                "GET /api/resources",
                "progress:resources",
            ],
        },
        {
            "id": "M24",
            "name": "Model factories",
            "status": "complete",
            "proof": [
                "Factory base, states, sequences",
                "has / for / has_attached / recycle",
                "make:factory; DemoSeeder builds every row",
                "progress:factories",
            ],
        },
        {
            "id": "M25",
            "name": "Articulate NoSQL",
            "status": "complete",
            "proof": [
                "Document models over Mongo and a memory store",
                "embeds, references, indexes, factories, soft deletes",
                "make:document; documents:index; documents:show",
                "GET /api/documents",
                "progress:documents",
                "articulate/documents/* — L13 Mongo parity map",
            ],
        },
        {
            "id": "M26",
            "name": "Broadcasting",
            "status": "complete",
            "proof": [
                "ShouldBroadcast events, queued or now, over log/websocket/redis/pusher",
                "routes/channels.py auth with model binding; presence rosters",
                "/broadcasting/auth and a websocket at /broadcasting/socket",
                "BroadcastsEvents models; broadcast notification channel",
                "make:channel; channel:list",
                "GET /api/broadcast",
                "progress:broadcast",
                "Echo-class client → M52",
            ],
        },
        {
            "id": "M27",
            "name": "Search",
            "status": "complete",
            "proof": [
                "Searchable models — index kept in step by model events",
                "database / collection / meilisearch / null engines + Scout.extend()",
                "where, order_by, pagination, keys, cursor; query_using()",
                "queued indexing, after-commit indexing, soft-delete flags",
                "scout:import / flush / index / sync-index-settings / status",
                "GET /api/search",
                "progress:search",
            ],
        },
        {
            "id": "M28",
            "name": "Testing toolkit",
            "status": "complete",
            "proof": [
                "TestCase + in-process TestClient over the real middleware",
                "TestResponse — status, headers, JSON, session, view assertions",
                "artisan() — expects_question / expects_output / assert_exit_code",
                "assert_database_has, refresh_database, database_transactions",
                "fake() — mail, queue, notification, storage, event, http, "
                "process, broadcast, scout",
                "travel / freeze_time; without_middleware",
                "tests/ in the scaffold; make:test; smith test",
                "progress:testing",
            ],
        },
        {
            "id": "M29",
            "name": "Package development",
            "status": "planned",
            "proof": ["provider discovery", "publish tags", "package guidelines"],
        },
        {
            "id": "M30",
            "name": "Smith Console exhaust",
            "status": "complete",
            "proof": [
                "102 commands, every one a Command class",
                "full signature parser + option shortcuts",
                "Artisan.call / queue / output + closure commands",
                "--isolated locks · trap · with_progress_bar",
                "stub:publish · vendor:publish · cache/view/optimize",
                "db:show / db:table / model:show · migrate:reset / refresh",
                "smith progress:console · smith progress:import",
            ],
        },
        {
            "id": "M31",
            "name": "Task scheduling exhaust",
            "status": "complete",
            "proof": [
                "frequency + constraint + hook vocabulary",
                "sub-minute tasks · groups · one server · background",
                "output to file / mail · lifecycle events",
                "schedule:list / test / interrupt / clear-cache · down / up",
                "smith progress:schedule",
            ],
        },
        {
            "id": "M32",
            "name": "Installer + scaffold stacks",
            "status": "complete",
            "proof": [
                "smith progress:install",
                "almasix new asks: stack, database, tests, git, install",
                "tailwind / bootstrap / plain / none — a stub tree, not strings",
                "sqlite / pgsql / mysql / mariadb write .env + config",
                "default migrations: users, sessions, cache, jobs",
                "@vite tags · cache:table / queue:table / session:table",
            ],
        },
        {
            "id": "M33",
            "name": "Routing DX + named routes",
            "status": "complete",
            "proof": [
                "smith progress:routing",
                "head / match / any / redirect / view / fallback",
                "route() · signed_route() · action() · to_route()",
                "resource / api_resource / singleton — nested, shallow, scoped",
                "where + global patterns · optional {name?} · domains",
                "implicit binding · missing() · _method spoofing",
                "smith route:list --middleware --sort=name",
            ],
        },
        {
            "id": "M34",
            "name": "Security headers + CORS",
            "status": "complete",
            "proof": [
                "smith progress:security",
                "X-Content-Type-Options / X-Frame-Options / Referrer-Policy",
                "CSP nonce · HSTS opt-in · csp_nonce() in Prism",
                "config/cors.py · HandleCors on api/*",
                "smith down --secret --retry · 503 + bypass cookie",
            ],
        },
        {
            "id": "M35",
            "name": "Rate limiting",
            "status": "complete",
            "proof": [
                "smith progress:rate-limiting",
                "RateLimiter.attempt / hit / remaining / clear",
                "throttle:60,1 · throttle:api · named Limit.per_*",
                "X-RateLimit-* + Retry-After on 429",
                "LoginRateLimiter + attempt_login",
            ],
        },
        {
            "id": "M36",
            "name": "Starter kits",
            "status": "planned",
            "proof": ["web / API / SPA kits"],
        },
        {
            "id": "M37",
            "name": "API tokens + social auth",
            "status": "planned",
            "proof": ["Sanctum-class tokens", "Socialite-class providers"],
        },
        {
            "id": "M38",
            "name": "Deployment + production ops",
            "status": "complete",
            "proof": [
                "smith progress:deploy",
                "smith serve --workers",
                "GET /up health probe",
                "docs/deployment + examples/deploy",
                "PyPI Trusted Publishing (0.4.0 ready)",
            ],
        },
        {
            "id": "M39",
            "name": "Docs journey rewrite + Prologue",
            "status": "complete",
            "proof": [
                "smith progress:docs",
                "Prologue: intro / release notes / upgrade / versions",
                "Basics teaching order + auth in Basics",
                "header version switcher (latest major + main)",
                "older-docs banner when not latest",
                "no milestone IDs in Starlight",
            ],
        },
        {
            "id": "M40",
            "name": "Articulate model exhaust",
            "status": "complete",
            "proof": [
                "Attribute accessors + custom casts",
                "encrypted / hashed casts · with_casts",
                "User.display_name append · GET /api/users",
                "Prunable Post + smith model:prune",
                "UUID/ULID keys · strictness · quiet writes",
            ],
        },
        {
            "id": "M41",
            "name": "Relationship exhaust",
            "status": "complete",
            "proof": [
                "GET /api/orm relationship tour",
                "pivot objects · using / as_ / with_timestamps",
                "with_sum / with_exists · load_count family",
                "latest_of_many · with_default · chaperone",
                "morph maps · touches · where_has_morph",
            ],
        },
        {
            "id": "M42",
            "name": "Query builder + database exhaust",
            "status": "complete",
            "proof": [
                "smith progress:queries",
                "JSON wheres + JSON updates · unions · locking",
                "join_sub / join_lateral · sole · implode",
                "read/write + sticky · DB.listen · DB.pretend",
                "smith db · db:show / db:table / db:monitor",
            ],
        },
        {
            "id": "M43",
            "name": "Schema, migrations, pagination",
            "status": "complete",
            "proof": [
                "smith progress:schema",
                "the column catalogue · change() · drops · Schema.rename",
                "get_indexes / get_foreign_keys · without_foreign_key_constraints",
                "migrate --pretend / --step / --path · schema:dump",
                "cursor_paginate · URL-aware links() through Prism",
            ],
        },
        {
            "id": "M44",
            "name": "Multi-engine database CI",
            "status": "complete",
            "proof": [
                "smith progress:engines",
                "CI orm-engines: sqlite + pgsql + mysql",
                "tests/test_m44_conformance.py",
                "database/engines support matrix",
            ],
        },
        {
            "id": "M45",
            "name": "Prism language support",
            "status": "planned",
            "proof": [".prism.html grammar", "syntax highlighting"],
        },
        {
            "id": "M46",
            "name": "Almasix Language Server",
            "status": "planned",
            "proof": ["almasix-lsp", "completion + go-to-definition"],
        },
        {
            "id": "M47",
            "name": "Editor integrations + stubs",
            "status": "planned",
            "proof": ["VS Code + JetBrains plugins", "smith ide:stubs"],
        },
        {
            "id": "M48",
            "name": "AI agent support",
            "status": "planned",
            "proof": ["smith mcp server", "agent guidelines"],
        },
        {
            "id": "M49",
            "name": "Support Collections exhaust",
            "status": "complete",
            "proof": [
                "smith progress:collections",
                "LazyCollection + async twin (Model.cursor)",
                "higher order messages",
                "155 documented methods",
            ],
        },
        {
            "id": "M50",
            "name": "Helpers + Str exhaust",
            "status": "complete",
            "proof": [
                "smith progress:helpers",
                "Stringable delegates the Str surface",
                "app / request / response / session / validator",
                "377 documented methods",
            ],
        },
        {
            "id": "M51",
            "name": "Lint and format gate",
            "status": "complete",
            "proof": [
                "smith progress:lint",
                "ruff==0.16.6 pinned",
                "make lint = check + format --check",
                "CI lint job on 3.11–3.13",
            ],
        },
        {
            "id": "M52",
            "name": "Echo-class broadcasting client",
            "status": "planned",
            "proof": ["browser client package", "private/presence auth", "Vite install path"],
        },
    ]


def _count(milestones: list[dict], status: str) -> int:
    return len([m for m in milestones if m["status"] == status])


def _board() -> dict:
    milestones = _milestones()
    return {
        "framework": "almasix",
        "version": __version__,
        "app": str(config("app.name")),
        "completed": _count(milestones, "complete"),
        "in_progress": _count(milestones, "partial"),
        "planned": _count(milestones, "planned") + _count(milestones, "next"),
        "total": len(milestones),
        "milestones": milestones,
    }


class ProgressController(Controller):
    async def index(self) -> Response:
        board = _board()
        milestones = [{**m, "proof_text": ", ".join(m["proof"])} for m in board["milestones"]]
        upcoming = next((m["id"] for m in board["milestones"] if m["status"] == "next"), None)
        return view(
            "progress",
            {
                "completed": board["completed"],
                "in_progress": board["in_progress"],
                "total": board["total"],
                "next_id": upcoming,
                "version": board["version"],
                "milestones": milestones,
                "home_url": url("/", absolute=False),
                "api_url": url("/api/progress", absolute=False),
            },
        )

    async def data(self) -> dict:
        return _board()
