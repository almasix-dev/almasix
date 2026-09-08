"""Milestone board — HTML on the web route, JSON on the API route."""

from __future__ import annotations

from avalon import __version__
from avalon.caliburn import view
from avalon.config import config
from avalon.http import Controller, Response
from avalon.routing import url


def _milestones() -> list[dict]:
    # Keep in sync with docs/PLAN.md as milestones land.
    return [
        {
            "id": "M0",
            "name": "Skeleton",
            "status": "complete",
            "proof": ["avalon new", "python grail serve", "examples/progress scaffold"],
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
                "python grail make:controller/middleware/provider/request",
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
            "status": "partial",
            "proof": [
                "GET /api/orm feature tour",
                "eager load / soft deletes / pivot / morphs",
                "grail migrate / make:model",
                "ladder shipped — query builder + schema owed by M42/M43",
            ],
        },
        {
            "id": "M6",
            "name": "Caliburn",
            "status": "complete",
            "proof": [
                ".cal.html layouts + @foreach",
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
                "Command base + grail list",
                "schedule:run / schedule:work",
                "grail fiddle REPL",
                "Avalon Prompts + dump()/dd()",
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
                "progress:helpers",
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
            "status": "planned",
            "proof": ["Process::run / pool", "subprocess fakes"],
        },
        {
            "id": "M22",
            "name": "Concurrency",
            "status": "planned",
            "proof": ["Concurrency::run", "async / process drivers"],
        },
        {
            "id": "M23",
            "name": "API Resources",
            "status": "planned",
            "proof": ["JsonResource / ResourceCollection", "make:resource"],
        },
        {
            "id": "M24",
            "name": "Model factories",
            "status": "planned",
            "proof": ["Factory base", "states / sequences", "make:factory"],
        },
        {
            "id": "M25",
            "name": "Articulate NoSQL",
            "status": "planned",
            "proof": ["Mongo document models", "multi-store Articulate"],
        },
        {
            "id": "M26",
            "name": "Broadcasting",
            "status": "planned",
            "proof": ["ShouldBroadcast", "channel auth", "Redis / websocket"],
        },
        {
            "id": "M27",
            "name": "Search",
            "status": "planned",
            "proof": ["Searchable models", "Scout-class drivers"],
        },
        {
            "id": "M28",
            "name": "Testing toolkit",
            "status": "planned",
            "proof": ["HTTP / console assertions", "façade fakes"],
        },
        {
            "id": "M29",
            "name": "Package development",
            "status": "planned",
            "proof": ["provider discovery", "publish tags", "package guidelines"],
        },
        {
            "id": "M30",
            "name": "Grail Console exhaust",
            "status": "partial",
            "proof": [
                "full signature parser + option shortcuts",
                "Artisan.call / queue / output + closure commands",
                "--isolated locks · trap · with_progress_bar",
                "progress:console · progress:import",
                "owed: one command surface · stub:publish · built-ins",
            ],
        },
        {
            "id": "M31",
            "name": "Task scheduling exhaust",
            "status": "planned",
            "proof": ["frequency + hook vocabulary", "schedule:list / schedule:test"],
        },
        {
            "id": "M32",
            "name": "Installer + scaffold stacks",
            "status": "planned",
            "proof": ["interactive avalon new", "tailwind / bootstrap / plain CSS"],
        },
        {
            "id": "M33",
            "name": "Routing DX + named routes",
            "status": "planned",
            "proof": ["match / any / fallback / redirect", "route() + resources"],
        },
        {
            "id": "M34",
            "name": "Security headers + CORS",
            "status": "planned",
            "proof": ["header middleware", "CORS middleware"],
        },
        {
            "id": "M35",
            "name": "Rate limiting",
            "status": "planned",
            "proof": ["RateLimiter façade", "throttle middleware"],
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
            "status": "planned",
            "proof": ["grail serve --workers", "optimize / cache warm"],
        },
        {
            "id": "M39",
            "name": "Docs versioning + Prologue",
            "status": "planned",
            "proof": ["major-version switching", "Prologue sidebar group"],
        },
        {
            "id": "M40",
            "name": "Articulate model exhaust",
            "status": "complete",
            "proof": [
                "Attribute accessors + custom casts",
                "encrypted / hashed casts · with_casts",
                "User.display_name append · GET /api/users",
                "Prunable Post + grail model:prune",
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
            "status": "next",
            "proof": [
                "unions · locking · JSON wheres",
                "read/write connections · DB.listen",
                "db:show / db:table / db:monitor",
            ],
        },
        {
            "id": "M43",
            "name": "Schema, migrations, pagination",
            "status": "planned",
            "proof": ["column alteration", "cursor pagination", "migrate:refresh"],
        },
        {
            "id": "M44",
            "name": "Multi-engine database CI",
            "status": "planned",
            "proof": ["Postgres + MySQL test matrix"],
        },
        {
            "id": "M45",
            "name": "Caliburn language support",
            "status": "planned",
            "proof": [".cal.html grammar", "syntax highlighting"],
        },
        {
            "id": "M46",
            "name": "Avalon Language Server",
            "status": "planned",
            "proof": ["avalon-lsp", "completion + go-to-definition"],
        },
        {
            "id": "M47",
            "name": "Editor integrations + stubs",
            "status": "planned",
            "proof": ["VS Code + JetBrains plugins", "grail ide:stubs"],
        },
        {
            "id": "M48",
            "name": "AI agent support",
            "status": "planned",
            "proof": ["grail mcp server", "agent guidelines"],
        },
        {
            "id": "M49",
            "name": "Support Collections exhaust",
            "status": "complete",
            "proof": ["LazyCollection + async twin", "higher-order messages", "155 documented methods"],
        },
        {
            "id": "M50",
            "name": "Helpers + Str exhaust",
            "status": "complete",
            "proof": ["fluent Stringable delegates Str", "global helpers", "377 documented methods"],
        },
    ]


def _count(milestones: list[dict], status: str) -> int:
    return len([m for m in milestones if m["status"] == status])


def _board() -> dict:
    milestones = _milestones()
    return {
        "framework": "avalon",
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
        milestones = [
            {**m, "proof_text": ", ".join(m["proof"])}
            for m in board["milestones"]
        ]
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
