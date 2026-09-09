"""Searching with Meilisearch.

Everything here goes through Almasix's own HTTP client, so there is no SDK to
install, `Http.fake()` fakes search too, and the requests are the ones you
would read about in Meilisearch's API reference.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from almasix.scout.builder import SOFT_DELETED
from almasix.scout.engines.base import Engine, searchable_payload
from almasix.scout.exceptions import SearchException


class MeilisearchEngine(Engine):
    """The `meilisearch` driver — a real index, over HTTP."""

    driver = "meilisearch"

    @property
    def host(self) -> str:
        return str(self.config.get("host") or "http://localhost:7700").rstrip("/")

    @property
    def key(self) -> str | None:
        value = self.config.get("key")
        return str(value) if value else None

    # --- writing ------------------------------------------------------------

    async def update(self, models: Sequence[Any]) -> None:
        records = list(models)
        if not records:
            return
        index = records[0].searchable_as()
        primary = records[0].get_scout_key_name()
        documents = [searchable_payload(model) for model in records]
        await self._request("PUT", f"/indexes/{index}/documents?primaryKey={primary}", documents)

    async def delete(self, models: Sequence[Any]) -> None:
        records = list(models)
        if not records:
            return
        index = records[0].searchable_as()
        keys = [model.get_scout_key() for model in records]
        await self._request("POST", f"/indexes/{index}/documents/delete-batch", keys)

    async def flush(self, model: Any) -> None:
        await self._request("DELETE", f"/indexes/{model.searchable_as()}/documents")

    async def create_index(self, name: str, options: Mapping[str, Any] | None = None) -> Any:
        body = {"uid": name, "primaryKey": str((options or {}).get("primaryKey") or "id")}
        return await self._request("POST", "/indexes", body)

    async def delete_index(self, name: str) -> Any:
        return await self._request("DELETE", f"/indexes/{name}")

    async def delete_all_indexes(self) -> Any:
        listing = await self._request("GET", "/indexes?limit=1000")
        for index in listing.get("results") or []:
            await self.delete_index(str(index.get("uid")))
        return listing

    async def sync_settings(self, model: Any) -> bool:
        """Push `index-settings` for a model, adding soft deletes when it needs them."""
        settings = dict(self._settings_for(model))
        if getattr(model, "_soft_deletes", False) and model.uses_soft_delete_metadata():
            filterable = list(settings.get("filterableAttributes") or [])
            if SOFT_DELETED not in filterable:
                filterable.append(SOFT_DELETED)
            settings["filterableAttributes"] = filterable
        if not settings:
            return False
        await self._request("PATCH", f"/indexes/{model.searchable_as()}/settings", settings)
        return True

    def _settings_for(self, model: Any) -> Mapping[str, Any]:
        """Index settings may be keyed by model class, class path, or index name."""
        configured = self.config.get("index-settings") or {}
        for key, settings in configured.items():
            if key is model:
                return settings
            if isinstance(key, str) and key in {
                model.searchable_as(),
                model.__name__,
                f"{model.__module__}.{model.__qualname__}",
            }:
                return settings
        return {}

    # --- reading ------------------------------------------------------------

    async def search(self, builder: Any) -> Any:
        return await self._search(builder, self._payload(builder, limit=builder.limit))

    async def paginate(self, builder: Any, per_page: int, page: int) -> Any:
        payload = self._payload(builder, limit=None)
        payload["hitsPerPage"] = int(per_page)
        payload["page"] = max(int(page), 1)
        return await self._search(builder, payload)

    async def _search(self, builder: Any, payload: dict[str, Any]) -> Any:
        index = builder.index or builder.model.searchable_as()
        if builder.callback is not None:
            answer = builder.callback(self, builder.query, payload)
            return await answer if hasattr(answer, "__await__") else answer
        return await self._request("POST", f"/indexes/{index}/search", payload)

    def _payload(self, builder: Any, *, limit: int | None) -> dict[str, Any]:
        payload: dict[str, Any] = {"q": builder.query, **builder.search_options}
        filters = _filters(builder)
        if filters:
            payload["filter"] = filters
        if builder.orders:
            payload["sort"] = [
                f"{order['column']}:{order['direction']}" for order in builder.orders
            ]
        if limit:
            payload["limit"] = int(limit)
        return payload

    def map_ids(self, results: Any) -> list[Any]:
        hits = results.get("hits") or []
        if not hits:
            return []
        # Meilisearch answers with whole documents; the primary key is the one
        # the index was created with, and `id` unless a model said otherwise.
        key = "id" if "id" in hits[0] else next(iter(hits[0]))
        return [hit.get(key) for hit in hits]

    def total_count(self, results: Any) -> int:
        for field in ("totalHits", "estimatedTotalHits", "nbHits"):
            if field in results:
                return int(results[field])
        return len(results.get("hits") or [])

    # --- the wire ------------------------------------------------------------

    async def _request(self, method: str, path: str, body: Any = None) -> Any:
        from almasix.client.facade import Http

        pending = Http.pending().base_url(self.host).as_json()
        if self.key:
            pending = pending.with_token(self.key)

        response = await pending.send_async(method, path, body)
        if not response.successful():
            raise SearchException(
                f"Meilisearch answered {response.status()} for {method} {path}: {response.body()}"
            )
        return response.json() or {}


def _filters(builder: Any) -> str:
    """Meilisearch's filter expression for the builder's clauses."""
    parts: list[str] = []
    for field, value in builder.wheres.items():
        parts.append(f"{field} = {_literal(value)}")
    for field, values in builder.where_ins.items():
        parts.append(f"{field} IN [{', '.join(_literal(value) for value in values)}]")
    for field, values in builder.where_not_ins.items():
        parts.append(f"{field} NOT IN [{', '.join(_literal(value) for value in values)}]")
    return " AND ".join(parts)


def _literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace('"', '\\"')
    return f'"{escaped}"'
