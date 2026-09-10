"""Inertia SSR via Node worker (HTTP contract)."""

from __future__ import annotations

import json
from typing import Any

from almasix.config import config


def _cfg(key: str, default: Any = None) -> Any:
    try:
        value = config(key, default)
    except RuntimeError:
        return default
    return default if value is None else value


def render_ssr(page: dict[str, Any]) -> dict[str, str] | None:
    """POST page JSON to the Node SSR server; return ``{head, body}`` or None."""
    url = str(_cfg("inertia.ssr_url", "http://127.0.0.1:13714")).rstrip("/")
    try:
        import httpx

        response = httpx.post(
            f"{url}/render",
            content=json.dumps(page, default=str),
            headers={"Content-Type": "application/json"},
            timeout=2.0,
        )
        if response.status_code != 200:
            return None
        data = response.json()
        if not isinstance(data, dict):
            return None
        head = data.get("head") or []
        if isinstance(head, list):
            head_html = "".join(str(h) for h in head)
        else:
            head_html = str(head)
        return {"head": head_html, "body": str(data.get("body") or "")}
    except Exception:
        return None
