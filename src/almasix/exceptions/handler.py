"""Exception Handler — ``report`` / ``render`` split."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from fastapi.responses import JSONResponse
from starlette.responses import HTMLResponse
from starlette.responses import Response as StarletteResponse

from almasix.exceptions.debug import render_debug_html
from almasix.exceptions.mapping import (
    ERROR_STATUSES,
    default_message_for_status,
    status_for_exception,
)
from almasix.http.exceptions import HttpException
from almasix.http.response import html
from almasix.log import log

if TYPE_CHECKING:
    from almasix.framework.application import Application
    from almasix.http.request import Request

ReportCallback = Callable[[BaseException], bool | None]
RenderCallback = Callable[[Any, BaseException], StarletteResponse | None]


def _app_name() -> str:
    try:
        from almasix.config import config

        return str(config("app.name", "Almasix"))
    except Exception:
        return "Almasix"


class Handler:
    """Application exception handler (Laravel-shaped)."""

    dont_report: list[type[BaseException]] = []

    def __init__(self, app: Application | None = None) -> None:
        self.app = app
        self._reportable: list[tuple[type[BaseException], ReportCallback]] = []
        self._renderable: list[tuple[type[BaseException], RenderCallback]] = []

    def reportable(self, exc_type: type[BaseException], callback: ReportCallback) -> None:
        self._reportable.append((exc_type, callback))

    def renderable(self, exc_type: type[BaseException], callback: RenderCallback) -> None:
        self._renderable.append((exc_type, callback))

    def should_report(self, exc: BaseException) -> bool:
        from almasix.debug import DumpAndDie

        if isinstance(exc, DumpAndDie):
            return False
        if status_for_exception(exc) < 500:
            return False
        for cls in self.dont_report:
            if isinstance(exc, cls):
                return False
        return True

    def report(self, exc: BaseException) -> None:
        for exc_type, callback in self._reportable:
            if isinstance(exc, exc_type):
                result = callback(exc)
                if result is False:
                    return
                if result is True:
                    break

        report_fn = getattr(exc, "report", None)
        if callable(report_fn):
            outcome = report_fn()
            if outcome is False:
                return

        if not self.should_report(exc):
            return

        logger = log().with_(exception=type(exc).__name__)
        if isinstance(exc, HttpException) and exc.status_code < 500:
            logger.warning("%s: %s", type(exc).__name__, exc)
            return
        logger.exception("%s: %s", type(exc).__name__, exc)

    def render(self, request: Request, exc: BaseException) -> StarletteResponse:
        from almasix.debug import DumpAndDie

        for exc_type, callback in self._renderable:
            if isinstance(exc, exc_type):
                response = callback(request, exc)
                if response is not None:
                    return response

        render_fn = getattr(exc, "render", None)
        if callable(render_fn):
            response = render_fn(request)
            if response is not None:
                return response

        if isinstance(exc, DumpAndDie):
            return self._render_dd(request, exc)

        if self._is_api(request):
            return self._render_json(request, exc)
        return self._render_html(request, exc)

    def _render_dd(self, request: Request, exc: Any) -> StarletteResponse:
        from almasix.console.display import serialize
        from almasix.debug import render_dd_html

        if self._is_api(request):
            return JSONResponse(
                {
                    "dd": True,
                    "caller": str(exc.caller) if exc.caller else None,
                    "function": exc.caller.function if exc.caller else None,
                    "values": [serialize(value) for value in exc.values],
                },
                status_code=200,
            )

        app_name = "Almasix"
        if self.app is not None:
            app_name = str(self.app.config.get("app.name", "Almasix"))
        body = render_dd_html(
            tuple(exc.values),
            caller=exc.caller,
            request_method=request.method,
            request_path=request.path,
            app_name=app_name,
        )
        return HTMLResponse(body, status_code=200)

    def _is_api(self, request: Request) -> bool:
        polarity = getattr(request, "route_polarity", None)
        if polarity == "api":
            return True
        if polarity == "web":
            return False
        # No polarity (ASGI-level / unknown): preserve M2 JSON floor when unset.
        return True

    def _debug(self) -> bool:
        if self.app is None:
            return False
        return bool(self.app.config.get("app.debug", False))

    def _status_for(self, exc: BaseException) -> int:
        return status_for_exception(exc)

    def _message_for(self, exc: BaseException, *, for_client: bool) -> str:
        status = self._status_for(exc)
        if isinstance(exc, HttpException):
            if for_client and status >= 500 and not self._debug():
                return default_message_for_status(status)
            return str(exc.message)
        if for_client and self._debug():
            return str(exc) or type(exc).__name__
        if for_client:
            return default_message_for_status(status)
        return str(exc) or type(exc).__name__

    def _render_json(self, request: Request, exc: BaseException) -> JSONResponse:
        del request  # polarity already decided
        status = self._status_for(exc)
        if isinstance(exc, HttpException):
            payload = exc.to_dict()
            if status >= 500 and not self._debug():
                payload = {
                    "message": default_message_for_status(status),
                    "status": status,
                    "errors": {},
                }
            return JSONResponse(
                payload,
                status_code=status,
                headers=exc.headers or None,
            )
        message = self._message_for(exc, for_client=True)
        return JSONResponse(
            {"message": message, "status": status, "errors": {}},
            status_code=status,
        )

    def _render_html(self, request: Request, exc: BaseException) -> StarletteResponse:
        status = self._status_for(exc)
        if self._debug():
            body = render_debug_html(
                exc,
                request_method=request.method,
                request_path=request.path,
                route_name=getattr(request, "route_name", None),
                app_name=str(self.app.config.get("app.name", "Almasix") if self.app else "Almasix"),
            )
            return HTMLResponse(body, status_code=status)

        view_status = status if status in ERROR_STATUSES else 500
        if isinstance(exc, HttpException) and status < 500:
            message = str(exc.message)
        else:
            message = self._message_for(exc, for_client=True)

        rendered = self._try_view(f"errors.{view_status}", status, message)
        if rendered is not None:
            return rendered

        return html(self._fallback_html(view_status, message), status=status)

    def _try_view(
        self,
        name: str,
        status: int,
        message: str,
    ) -> HTMLResponse | None:
        try:
            from almasix.prism.helpers import get_engine, view
        except Exception:
            return None
        try:
            engine = get_engine()
        except RuntimeError:
            return None
        if not engine.exists(name):
            return None
        return view(
            name,
            {
                "status": status,
                "message": message,
                "name": _app_name(),
                "__authenticated": False,
            },
            status=status,
        )

    @staticmethod
    def _fallback_html(status: int, message: str) -> str:
        safe_message = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return (
            "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'/>"
            f"<title>{status}</title></head><body>"
            f"<h1>{status}</h1><p>{safe_message}</p></body></html>"
        )
