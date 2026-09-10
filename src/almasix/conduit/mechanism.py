"""Wire protocol — snapshot, checksum, coalesced updates, island payloads."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from typing import Any

from starlette.responses import JSONResponse

from almasix.conduit.component import Component
from almasix.conduit.manager import Conduit
from almasix.config import config
from almasix.http.request import Request
from almasix.prism.helpers import render
from almasix.validation.form_request import ValidationException


def _cfg(key: str, default: Any = None) -> Any:
    try:
        value = config(key, default)
    except RuntimeError:
        return default
    return default if value is None else value


def _checksum_key() -> str:
    return str(_cfg("conduit.checksum_key") or _cfg("app.key") or "conduit-dev-key")


def checksum(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hmac.new(_checksum_key().encode(), raw.encode(), hashlib.sha256).hexdigest()


def new_id() -> str:
    return str(uuid.uuid4())


def snapshot(component: Component) -> dict[str, Any]:
    component.dehydrate()
    data = component.get_public_properties()
    memo = {
        "data": data,
        "errors": component.get_error_bag(),
        "checksum": "",
    }
    memo["checksum"] = checksum(
        {"data": data, "name": component.conduit_name, "id": component.conduit_id}
    )
    return {
        "fingerprint": {
            "id": component.conduit_id,
            "name": component.conduit_name,
            "path": "/",
            "method": "GET",
        },
        "serverMemo": memo,
    }


def verify_checksum(component: Component, memo: dict[str, Any]) -> bool:
    expected = checksum(
        {
            "data": memo.get("data") or {},
            "name": component.conduit_name,
            "id": component.conduit_id,
        }
    )
    provided = str(memo.get("checksum") or "")
    return bool(provided) and secrets.compare_digest(expected, provided)


def render_html(component: Component, *, island: str | None = None) -> str:
    if not component.should_render():
        return ""
    component.rendering()
    if island:
        view = component.render_island(island) or component.render()
    else:
        view = component.render()
    ctx = component.get_public_properties()
    ctx["errors"] = component.get_error_bag()
    ctx["this"] = component
    # Single-file style: ``render()`` may return raw HTML instead of a view name.
    if isinstance(view, str) and view.lstrip().startswith("<"):
        html = view
    else:
        html = render(view, ctx)
    return component.rendered(html)


def wrap_root(component: Component, html: str, snap: dict[str, Any]) -> str:
    cid = component.conduit_id or new_id()
    component.conduit_id = cid
    encoded = (
        json.dumps(snap, separators=(",", ":"), default=str)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    stripped = html.strip()
    attrs = (
        f' wire:id="{cid}" wire:name="{component.conduit_name}"'
        f' data-conduit wire:initial-data="{encoded}"'
    )
    if stripped.startswith("<") and ">" in stripped:
        gt = stripped.index(">")
        tag = stripped[:gt]
        if tag.endswith("/"):
            return tag[:-1] + attrs + "/>" + stripped[gt + 1 :]
        return tag + attrs + ">" + stripped[gt + 1 :]
    return f"<div{attrs}>{stripped}</div>"


def embed_component(component: Component, *, lazy_force: bool = False) -> str:
    if component.conduit_id is None:
        component.conduit_id = new_id()
    if component.lazy or component.defer or lazy_force:
        return _embed_lazy(component, defer=component.defer and not component.lazy)

    component.mount()
    component.booted()
    snap = snapshot(component)
    html = render_html(component)
    return wrap_root(component, html, snap)


def _embed_lazy(component: Component, *, defer: bool = False) -> str:
    placeholder = component.lazy_placeholder
    body = (
        render(placeholder, component.get_public_properties())
        if placeholder
        else '<div class="conduit-lazy-placeholder" data-loading="true">Loading…</div>'
    )
    cid = component.conduit_id or new_id()
    component.conduit_id = cid
    mode = "defer" if defer else "lazy"
    return (
        f'<div wire:id="{cid}" wire:name="{component.conduit_name}" '
        f'wire:{mode}="true" data-conduit>{body}</div>'
    )


def hydrate_from_snapshot(
    name: str, memo: dict[str, Any], fingerprint: dict[str, Any]
) -> Component:
    component = Conduit.component(name)
    component.conduit_id = str(fingerprint.get("id") or new_id())
    component.conduit_name = name
    for key, value in (memo.get("data") or {}).items():
        if key in component._public_property_names():
            component.set_property(key, value)
    for key, msgs in (memo.get("errors") or {}).items():
        for msg in msgs if isinstance(msgs, list) else [msgs]:
            component.add_error(str(key), str(msg))
    component.hydrate()
    component.booted()
    return component


async def handle_update(request: Request) -> JSONResponse:
    payload = request.json()
    if not isinstance(payload, dict):
        payload = request.post() or {}
    if not isinstance(payload, dict):
        return JSONResponse({"message": "Invalid Conduit payload"}, status_code=400)

    components = payload.get("components")
    if components is None:
        components = [payload]
    if not isinstance(components, list):
        return JSONResponse({"message": "Invalid components list"}, status_code=400)

    results = [_update_one(entry, request) for entry in components if isinstance(entry, dict)]
    if len(results) == 1 and "components" not in payload:
        return JSONResponse(results[0])
    return JSONResponse({"components": results})


def _update_one(entry: dict[str, Any], request: Request) -> dict[str, Any]:
    fingerprint = entry.get("fingerprint") or {}
    memo = entry.get("serverMemo") or {}
    updates = entry.get("updates") or []
    calls = entry.get("calls") or []
    island = entry.get("island") or entry.get("islandTarget")
    name = str(fingerprint.get("name") or "")
    if not name:
        return {"effects": {"html": ""}, "serverMemo": {}, "error": "missing component name"}

    component = hydrate_from_snapshot(name, memo, fingerprint)
    provided_checksum = str(memo.get("checksum") or "")
    fresh = not provided_checksum and not (memo.get("data") or {})
    if not fresh and not verify_checksum(component, memo):
        return {"effects": {"html": ""}, "serverMemo": memo, "error": "checksum mismatch"}
    if fresh:
        component.mount()

    component.apply_query_string(request.query() or {})
    # Keep fingerprint.path aligned with the live request (subpath mount strips prefix).
    if isinstance(fingerprint, dict):
        fingerprint = {**fingerprint, "path": request.path or fingerprint.get("path") or "/"}

    for update in updates:
        if isinstance(update, (list, tuple)) and len(update) >= 2:
            prop, value = update[0], update[1]
            if isinstance(prop, str) and prop in component._public_property_names():
                component.set_property(prop, value)
        elif isinstance(update, dict):
            payload = update.get("payload") or update
            prop = payload.get("name") or update.get("name")
            value = payload.get("value", update.get("value"))
            if isinstance(prop, str) and prop in component._public_property_names():
                component.set_property(prop, value)

    renderless = False
    for call in calls:
        if not isinstance(call, dict):
            continue
        method = call.get("method") or call.get("path")
        params = call.get("params") or []
        meta = call.get("meta") or {}
        if call.get("island"):
            island = call.get("island")
        if meta.get("renderless") or call.get("renderless"):
            renderless = True
        if not isinstance(method, str):
            continue
        if method == "$set" and len(params) >= 2:
            prop, value = params[0], params[1]
            if isinstance(prop, str) and prop in component._public_property_names():
                component.set_property(prop, value)
            continue
        if method in {"$refresh", "$commit"}:
            continue
        if method == "$load":
            component.mount()
            continue
        try:
            component.call(method, *list(params))
        except ValidationException as exc:
            component.reset_error_bag()
            for key, msgs in (exc.errors or {}).items():
                for msg in msgs if isinstance(msgs, list) else [msgs]:
                    component.add_error(str(key), str(msg))
        except Exception as exc:  # pragma: no cover
            component.add_error("_method", str(exc))

    if renderless:
        component.renderless()
    if island:
        component.target_island(str(island))

    effects: dict[str, Any] = {
        "dispatches": component.take_dispatches(),
        "dirty": list(component.get_public_properties().keys()),
    }
    qs = component.sync_query_string()
    if qs:
        effects["queryString"] = qs

    # Always push memo data so client can do wire:bind / wire:text without morph.
    snap = snapshot(component)
    effects["data"] = snap["serverMemo"]["data"]
    effects["errors"] = snap["serverMemo"]["errors"]

    island_name = component.take_island() or (str(island) if island else None)
    if component.should_render():
        html = render_html(component, island=island_name if island_name else None)
        if island_name and not component.render_island(island_name):
            # Full render; client extracts [wire:island="name"].
            html = wrap_root(component, html, snap)
            effects["html"] = html
            effects["island"] = island_name
        elif island_name:
            effects["islands"] = {island_name: html}
        else:
            html = wrap_root(component, html, snap)
            effects["html"] = html
    else:
        component.reset_skip_render()

    # Rotate the signed update URL so long-lived tabs keep a fresh HMAC.
    from almasix.conduit.signing import public_signed_update_url

    effects["endpoint"] = public_signed_update_url()

    return {
        "effects": effects,
        "serverMemo": snap["serverMemo"],
        "fingerprint": snap["fingerprint"],
    }


def conduit_public_paths() -> dict[str, str]:
    """Subpath-aware public URLs for the Conduit client (honors ``APP_BASE_PATH``).

    The update endpoint is **relatively signed** (HMAC + expiry) on the internal
    path ``/conduit/update``; ``APP_BASE_PATH`` is prefixed only for the browser.
    """
    from almasix.conduit.signing import public_signed_update_url
    from almasix.routing.url import url

    asset_cfg = str(_cfg("conduit.asset_url", "/conduit/conduit.js") or "/conduit/conduit.js")
    upload_cfg = "/conduit/upload"
    return {
        "base": url("/", absolute=False).rstrip("/") or "",
        "endpoint": public_signed_update_url(),
        "asset": url(asset_cfg, absolute=False),
        "upload": url(upload_cfg, absolute=False),
    }


def conduit_assets_script() -> str:
    """Alpine + Conduit JS tags, with an inline config that survives subpath mounts."""
    paths = conduit_public_paths()
    csp_safe = bool(_cfg("conduit.csp_safe", False))
    alpine = _cfg(
        "conduit.alpine_csp_cdn" if csp_safe else "conduit.alpine_cdn",
        "https://cdn.jsdelivr.net/npm/@alpinejs/csp@3.x.x/dist/cdn.min.js"
        if csp_safe
        else "https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js",
    )
    config_json = json.dumps(
        {
            "base": paths["base"],
            "endpoint": paths["endpoint"],
            "asset": paths["asset"],
            "upload": paths["upload"],
            "coalesceMs": int(_cfg("conduit.coalesce_ms", 16) or 16),
            "signed": True,
        },
        separators=(",", ":"),
    )
    return (
        f"<script>window.__CONDUIT__={config_json};</script>\n"
        f'<meta name="conduit-endpoint" content="{paths["endpoint"]}">\n'
        f'<meta name="conduit-base" content="{paths["base"]}">\n'
        f'<script defer src="{alpine}"></script>\n'
        f'<script defer src="{paths["asset"]}"></script>'
    )
