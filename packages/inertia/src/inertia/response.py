"""Inertia response + façade (Responsable)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from typing import Any

from starlette.responses import HTMLResponse, JSONResponse, Response

from almasix.config import config
from almasix.http.request import Request, get_request
from almasix.prism.helpers import render


def _cfg(key: str, default: Any = None) -> Any:
    try:
        value = config(key, default)
    except RuntimeError:
        return default
    return default if value is None else value


class InertiaResponse:
    """Laravel-shaped Inertia response implementing ``to_response()``."""

    def __init__(
        self,
        component: str,
        props: Mapping[str, Any] | None = None,
        *,
        root_view: str | None = None,
        version: str | None = None,
    ) -> None:
        self.component = component
        self.props = dict(props or {})
        self.root_view = root_view
        self.version = version
        self._view_data: dict[str, Any] = {}

    def with_(self, key: str | Mapping[str, Any], value: Any = None) -> InertiaResponse:
        if isinstance(key, Mapping):
            self.props.update(dict(key))
        else:
            self.props[key] = value
        return self

    def with_view_data(self, key: str | Mapping[str, Any], value: Any = None) -> InertiaResponse:
        if isinstance(key, Mapping):
            self._view_data.update(dict(key))
        else:
            self._view_data[key] = value
        return self

    def to_response(self) -> Response:
        request = get_request()
        page = self._page(request)
        if request is not None and _is_inertia(request):
            return JSONResponse(
                page,
                headers={
                    "X-Inertia": "true",
                    "X-Inertia-Version": str(page.get("version") or ""),
                    "Vary": "X-Inertia",
                },
            )
        html = self._document(page)
        return HTMLResponse(html)

    def _page(self, request: Request | None) -> dict[str, Any]:
        shared = Inertia.all_shared()
        props = {**shared, **self.props}
        # Flash errors into shared props when a session is present.
        if request is not None:
            try:
                session = request.session
                errors = session.get("errors") if session is not None else None
                if errors and "errors" not in props:
                    props["errors"] = errors
            except Exception:
                pass
        props = _resolve_props(props, request=request)
        props = _filter_partial(request, self.component, props)
        version = self.version if self.version is not None else Inertia.version()
        url = "/"
        if request is not None:
            from almasix.routing.url import url as make_url

            # Public URL including APP_BASE_PATH when set.
            path = getattr(request, "path", None) or "/"
            raw_url = getattr(request, "url", "") or ""
            qs = ""
            if isinstance(raw_url, str) and "?" in raw_url:
                qs = "?" + raw_url.split("?", 1)[1]
            try:
                url = make_url(path, absolute=False) + qs
            except Exception:
                url = path + qs
        deferred = props.pop("_deferred", None)
        merge_props = props.pop("_mergeProps", None)
        page: dict[str, Any] = {
            "component": self.component,
            "props": props,
            "url": url,
            "version": version,
            "encryptHistory": False,
            "clearHistory": False,
        }
        if deferred:
            page["deferredProps"] = deferred
        if merge_props:
            page["mergeProps"] = merge_props
        return page

    def _document(self, page: dict[str, Any]) -> str:
        root = self.root_view or _cfg("inertia.root_view", "inertia::app")
        ssr = None
        if _cfg("inertia.ssr_enabled", False):
            from inertia.ssr import render_ssr

            ssr = render_ssr(page)
        ctx = {
            **self._view_data,
            "page": page,
            "page_json": json.dumps(page, default=str),
            "ssr_body": (ssr or {}).get("body", ""),
            "ssr_head": (ssr or {}).get("head", ""),
        }
        return render(root, ctx)


class Inertia:
    """Static façade: ``Inertia.render`` / ``share`` / ``location``."""

    _shared: dict[str, Any] = {}
    _shared_callbacks: list[Callable[[], Mapping[str, Any]]] = []
    _version: str | Callable[[], str] | None = None

    @classmethod
    def render(
        cls,
        component: str,
        props: Mapping[str, Any] | None = None,
        *,
        root_view: str | None = None,
    ) -> InertiaResponse:
        return InertiaResponse(component, props, root_view=root_view)

    @classmethod
    def share(
        cls, key: str | Mapping[str, Any] | Callable[[], Mapping[str, Any]], value: Any = None
    ) -> None:
        if callable(key) and not isinstance(key, str):
            cls._shared_callbacks.append(key)  # type: ignore[arg-type]
            return
        if isinstance(key, Mapping):
            cls._shared.update(dict(key))
            return
        cls._shared[str(key)] = value

    @classmethod
    def all_shared(cls) -> dict[str, Any]:
        data = dict(_cfg("inertia.shared") or {})
        data.update(cls._shared)
        for cb in cls._shared_callbacks:
            data.update(dict(cb()))
        return data

    @classmethod
    def set_version(cls, version: str | Callable[[], str]) -> None:
        cls._version = version

    @classmethod
    def version(cls) -> str:
        if cls._version is None:
            configured = _cfg("inertia.version")
            if configured:
                return str(configured)
            # Stable-ish default from app name + key fragment.
            raw = f"{_cfg('app.name')}:{_cfg('app.key')}"
            return hashlib.sha256(str(raw).encode()).hexdigest()[:12]
        if callable(cls._version):
            return str(cls._version())
        return str(cls._version)

    @classmethod
    def lazy(cls, callback: Callable[[], Any]) -> Any:
        from inertia.props import lazy

        return lazy(callback)

    @classmethod
    def optional(cls, callback: Callable[[], Any]) -> Any:
        from inertia.props import optional

        return optional(callback)

    @classmethod
    def defer(cls, callback: Callable[[], Any], *, group: str = "default") -> Any:
        from inertia.props import defer

        return defer(callback, group=group)

    @classmethod
    def once(cls, callback: Callable[[], Any]) -> Any:
        from inertia.props import once

        return once(callback)

    @classmethod
    def merge(cls, value: Any) -> Any:
        from inertia.props import merge

        return merge(value)

    @classmethod
    def location(cls, url: str) -> Response:
        """External redirect for Inertia (409 + X-Inertia-Location)."""
        request = get_request()
        if request is not None and _is_inertia(request):
            return Response(
                status_code=409,
                headers={"X-Inertia-Location": url},
            )
        from starlette.responses import RedirectResponse

        return RedirectResponse(url)


def _is_inertia(request: Request) -> bool:
    return str(request.header("X-Inertia") or "").lower() in {"true", "1"}


def _resolve_props(props: dict[str, Any], *, request: Request | None = None) -> dict[str, Any]:
    from inertia.props import DeferProp, LazyProp, MergeProp, OnceProp, OptionalProp

    partial = False
    only: set[str] = set()
    if request is not None:
        partial_component = request.header("X-Inertia-Partial-Component")
        only_header = request.header("X-Inertia-Partial-Data")
        if partial_component and only_header:
            partial = True
            only = {k.strip() for k in only_header.split(",") if k.strip()}

    out: dict[str, Any] = {}
    deferred: dict[str, list[str]] = {}
    merge_props: list[str] = []

    for key, value in props.items():
        if isinstance(value, (LazyProp, OptionalProp)):
            if not partial or key not in only:
                continue
            out[key] = value()
            continue
        if isinstance(value, DeferProp):
            if partial and key in only:
                out[key] = value()
            else:
                deferred.setdefault(value.group, []).append(key)
            continue
        if isinstance(value, OnceProp):
            out[key] = value()
            continue
        if isinstance(value, MergeProp):
            out[key] = value.resolve()
            merge_props.append(key)
            continue
        if callable(value) and not isinstance(value, type):
            out[key] = value()
        else:
            out[key] = value

    # Stash meta for page object (caller merges).
    out["__inertia_deferred"] = deferred
    out["__inertia_merge"] = merge_props
    return out


def _filter_partial(
    request: Request | None,
    component: str,
    props: dict[str, Any],
) -> dict[str, Any]:
    deferred = props.pop("__inertia_deferred", {})
    merge_props = props.pop("__inertia_merge", [])
    if request is None:
        props["_deferred"] = deferred if deferred else None
        if merge_props:
            props["_mergeProps"] = merge_props
        # Clean None deferred
        if props.get("_deferred") is None:
            props.pop("_deferred", None)
        return props
    partial_component = request.header("X-Inertia-Partial-Component")
    only = request.header("X-Inertia-Partial-Data")
    except_ = request.header("X-Inertia-Partial-Except")
    if not partial_component or partial_component != component:
        if deferred:
            props["_deferred"] = deferred
        if merge_props:
            props["_mergeProps"] = merge_props
        return props
    if only:
        keys = {k.strip() for k in only.split(",") if k.strip()}
        props = {k: v for k, v in props.items() if k in keys}
    if except_:
        skip = {k.strip() for k in except_.split(",") if k.strip()}
        props = {k: v for k, v in props.items() if k not in skip}
    return props
