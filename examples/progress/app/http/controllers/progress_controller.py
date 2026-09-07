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
            "name": "ORM",
            "status": "complete",
            "proof": [
                "GET /api/orm feature tour",
                "eager load / soft deletes / pivot / morphs",
                "grail migrate / make:model",
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
            "status": "next",
            "proof": ["dispatch / listen / subscribe", "queued listeners"],
        },
        {
            "id": "M19",
            "name": "Authorization",
            "status": "planned",
            "proof": ["Gates / Policies", "@can / @cannot", "make:policy"],
        },
        {
            "id": "M20",
            "name": "HTTP Client",
            "status": "planned",
            "proof": ["Http.get/post façade", "fakes / retry / pool"],
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
    ]


def _board() -> dict:
    milestones = _milestones()
    complete = [m for m in milestones if m["status"] == "complete"]
    return {
        "framework": "avalon",
        "version": __version__,
        "app": str(config("app.name")),
        "completed": len(complete),
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
        return view(
            "progress",
            {
                "completed": board["completed"],
                "total": board["total"],
                "version": board["version"],
                "milestones": milestones,
                "home_url": url("/", absolute=False),
                "api_url": url("/api/progress", absolute=False),
                "version": board["version"],
            },
        )

    async def data(self) -> dict:
        return _board()
