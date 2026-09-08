"""API routes — stateless, JSON responses.

Exhausts the M2 HTTP surface: verbs, nested groups, Request bag, container DI,
and HttpException shapes. The `api` middleware group carries `demo.tag`, so the
`X-Almasix-Demo` header proves group expansion end to end.

M5 ORM demos live under `/api/posts`, `/api/users`, and `/api/orm`; the M25
document-store demo lives under `/api/documents`, and the M26 broadcasting
demo under `/api/broadcast`.
"""

from app.http.controllers.broadcast_controller import BroadcastController
from app.http.controllers.demo_controller import DemoController
from app.http.controllers.document_controller import DocumentController
from app.http.controllers.health_controller import HealthController
from app.http.controllers.locale_controller import LocaleController
from app.http.controllers.orm_tour_controller import OrmTourController
from app.http.controllers.post_controller import PostController
from app.http.controllers.progress_controller import ProgressController
from app.http.controllers.resource_controller import ResourceController
from app.http.controllers.user_controller import UserController

from almasix.routing import Route

with Route.group(prefix="/api", middleware=["api"]):
    Route.get("/health", [HealthController, "index"])
    Route.get("/me", [HealthController, "me"], middleware=["auth:api"])
    Route.get("/ping", [DemoController, "ping"])
    Route.get("/progress", [ProgressController, "data"])
    Route.get("/locale", [LocaleController, "index"])
    Route.get("/orm", [OrmTourController, "index"])

    # M25 — Articulate over a document store, alongside the SQL demos above.
    Route.get("/documents", [DocumentController, "index"])

    # M26 — channels, authorization, and a socket, without a browser.
    Route.get("/broadcast", [BroadcastController, "index"])

    Route.get("/posts", [PostController, "index"])
    Route.get("/posts/pages", [PostController, "pages"])
    Route.get("/posts/trashed", [PostController, "trashed"])
    Route.post("/posts/{post}/trash", [PostController, "trash"])
    Route.post("/posts/{post}/restore", [PostController, "restore"])
    Route.get("/posts/{post}/comments", [PostController, "comments"])
    Route.post("/posts/{post}/comments", [PostController, "add_comment"])

    # M23 — API resources: the controller returns a resource, not a dict.
    Route.get("/resources", [ResourceController, "index"])
    Route.get("/resources/{post}", [ResourceController, "show"])

    Route.get("/users", [UserController, "index"])
    Route.get("/users/authors", [UserController, "authors"])
    Route.post("/users/upsert", [UserController, "upsert"])
    Route.get("/users/{user}/posts", [UserController, "posts"])
    Route.post("/users/{user}/roles/{role}", [UserController, "attach_role"])

    Route.get("/bag", [DemoController, "echo_bag"])
    Route.post("/bag", [DemoController, "echo_bag"])
    Route.get("/di", [DemoController, "with_config"])
    Route.options("/probe", [DemoController, "options_probe"])
    Route.get("/boom", [DemoController, "boom"])
    Route.get("/explode", [DemoController, "explode"])
    Route.get("/dd", [DemoController, "dump_demo"])
    Route.get("/missing", [DemoController, "missing"])
    Route.match(["GET", "POST"], "/echo/{item}", [DemoController, "show"])

    # Nested group: inherits the /api prefix and the `api` middleware group.
    with Route.group(prefix="/items"):
        Route.get("/{item}", [DemoController, "show"])
        Route.post("", [DemoController, "store"])
        Route.put("/{item}", [DemoController, "update"])
        Route.patch("/{item}", [DemoController, "patch"])
        Route.delete("/{item}", [DemoController, "destroy"])
