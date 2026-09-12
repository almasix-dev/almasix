"""Demo controller — Request bag, verbs, DI, HttpException, and FormRequest."""

from __future__ import annotations

from app.http.requests.store_item_request import StoreItemRequest

from almasix.config import ConfigRepository
from almasix.http import (
    Controller,
    HttpException,
    NotFoundHttpException,
    Request,
)


class DemoController(Controller):
    async def ping(self) -> dict[str, str]:
        return {"demo": "ping", "via": "controller"}

    async def show(self, request: Request, item: str) -> dict[str, object]:
        return {
            "item": item,
            "route": request.route("item"),
            "query": request.query("q"),
            "all": request.all(),
            "only_q": request.only("q"),
            "method": request.method,
            "path": request.path,
            "bearer": request.bearer_token(),
            "ip": request.ip(),
            "is_get": request.is_method("GET"),
        }

    async def store(self, request: StoreItemRequest) -> dict[str, object]:
        """M3: validation runs before this action; failures never reach here."""
        return {
            "created": True,
            "validated": request.validated(),
            "name": request.data.name,
            "integer_count": request.data.count,
            "boolean_flag": request.data.flag,
            "only": request.validated("name"),
            "post": request.post(),
        }

    async def store_inline(self, request: Request) -> dict[str, object]:
        """M3: ``request.validate(Schema)`` — Laravel ``$request->validate``."""
        data = request.validate(StoreItemRequest)
        return {"created": True, "via": "request.validate", "validated": data}

    async def validate_dsl(self, request: Request) -> dict[str, object]:
        """M56: pipe-string / Rule DSL on ``request.validate``."""
        data = request.validate(
            {
                "email": "required|email",
                "name": "required|string|min:2",
            }
        )
        return {"via": "dsl", "validated": data}

    async def echo_bag(self, request: Request) -> dict[str, object]:
        """Inspect the full Laravel-style input surface for one request."""
        return {
            "all": request.all(),
            "query": request.query(),
            "post": request.post(),
            "json": request.json(),
            "route": request.route(),
            "keys": request.keys(),
            "has_name": request.has("name"),
            "has_any": request.has_any("name", "q"),
            "filled_name": request.filled("name") if request.has("name") else False,
            "missing_x": request.missing("x"),
            "headers_accept": request.header("accept"),
            "user_agent": request.user_agent(),
            "is_json": request.is_json(),
            "files": list(request.files().keys()),
        }

    async def with_config(self, config: ConfigRepository) -> dict[str, object]:
        """Proves type-hinted container resolution into controller actions."""
        return {
            "injected": "ConfigRepository",
            "app_name": str(config.get("app.name")),
        }

    async def update(self, item: str) -> dict[str, object]:
        return {"updated": item}

    async def patch(self, item: str) -> dict[str, object]:
        return {"patched": item}

    async def destroy(self, item: str) -> dict[str, object]:
        return {"deleted": item}

    async def options_probe(self) -> dict[str, str]:
        return {"allow": "GET,POST,PUT,PATCH,DELETE,OPTIONS"}

    async def boom(self) -> dict[str, str]:
        raise HttpException("Intentional demo failure", status_code=418)

    async def explode(self) -> dict[str, str]:
        raise RuntimeError("Intentional demo failure")

    async def dump_demo(self) -> dict[str, str]:
        from almasix import dd

        dd({"milestone": "M9", "helper": "dd()"}, ["api", "json", "halt"])
        return {}  # pragma: no cover — dd() never returns

    async def missing(self) -> dict[str, str]:
        raise NotFoundHttpException("Demo resource not found")
