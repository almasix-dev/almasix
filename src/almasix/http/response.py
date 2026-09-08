"""Response helpers."""

from __future__ import annotations

from collections.abc import AsyncIterable, Iterable, Mapping
from pathlib import Path
from typing import Any

from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from starlette.responses import Response as StarletteResponse

__all__ = [
    "Redirect",
    "Response",
    "ResponseFactory",
    "back",
    "html",
    "json",
    "make_response",
    "redirect",
]


def make_response(
    content: Any = None,
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> StarletteResponse:
    """Normalize controller return values into an ASGI response."""
    if isinstance(content, StarletteResponse):
        if headers:
            for key, value in headers.items():
                content.headers[key] = value
        return content

    if content is None:
        return Response(status_code=status if status != 200 else 204, headers=headers)

    responder = getattr(content, "to_response", None)
    if callable(responder):
        # Laravel's Responsable: anything that can turn itself into a
        # response gets to, which is how API Resources come back from a
        # controller without the caller building the JSON.
        return make_response(responder(), status=status, headers=headers)

    if isinstance(content, (dict, list)):
        return JSONResponse(content, status_code=status, headers=headers)

    if isinstance(content, (bytes, bytearray)):
        return Response(content=bytes(content), status_code=status, headers=headers)

    return PlainTextResponse(str(content), status_code=status, headers=headers)


def json(
    data: Any,
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(data, status_code=status, headers=headers)


def html(
    content: str,
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> HTMLResponse:
    """Return an HTML response — the web-route counterpart to :func:`json`.

    Prefer ``almasix.prism.view()`` for templates; this helper remains for
    hand-built markup and low-level responses.
    """
    return HTMLResponse(content, status_code=status, headers=headers)


class Redirect(RedirectResponse):
    """A redirect that can flash data for the next request (Laravel's redirector)."""

    def with_(self, key: str | Mapping[str, Any], value: Any = None) -> Redirect:
        """Flash one value, or every pair in a mapping, for the next request."""
        values = dict(key) if isinstance(key, Mapping) else {str(key): value}
        session = _session()
        for name, item in values.items():
            session.flash(name, item)
        return self

    def with_input(self, values: Mapping[str, Any] | None = None) -> Redirect:
        """Flash input for ``old()`` — the current request's input by default."""
        if values is None:
            from almasix.http.request import get_request

            current = get_request()
            values = current.all() if current is not None else {}
        _session().flash("_old_input", dict(values))
        return self

    def with_errors(self, errors: Mapping[str, Any]) -> Redirect:
        """Flash an error bag, keyed by field, for the next request."""
        bag = {
            str(field): list(messages) if isinstance(messages, (list, tuple)) else [str(messages)]
            for field, messages in errors.items()
        }
        _session().flash("errors", bag)
        return self


def _session() -> Any:
    from almasix.session.store import get_session

    session = get_session()
    if session is None:
        raise RuntimeError(
            "Flashing needs a session. Add StartSession to the web middleware group."
        )
    return session


def redirect(
    to: str,
    *,
    status: int = 302,
    headers: dict[str, str] | None = None,
) -> Redirect:
    """Redirect to `to`, resolved through `APP_URL` / `APP_BASE_PATH`."""
    from almasix.routing.url import url

    return Redirect(url(to, absolute=False), status_code=status, headers=headers)


def back(
    fallback: str = "/",
    *,
    status: int = 302,
    headers: dict[str, str] | None = None,
) -> Redirect:
    """Redirect to the previous page (Laravel ``back``).

    Almasix reads the ``Referer`` header rather than a session-stored previous
    URL, so a request that arrives without one lands on ``fallback``.
    """
    from almasix.http.request import get_request

    current = get_request()
    previous = current.header("referer") if current is not None else None
    return Redirect(str(previous or fallback), status_code=status, headers=headers)


class ResponseFactory:
    """Laravel's response factory — what ``response()`` returns with no content."""

    def make(
        self,
        content: Any = None,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> StarletteResponse:
        return make_response(content, status=status, headers=headers)

    def json(
        self,
        data: Any,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> JSONResponse:
        return json(data, status=status, headers=headers)

    def html(
        self,
        content: str,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> HTMLResponse:
        return html(content, status=status, headers=headers)

    def no_content(
        self,
        *,
        status: int = 204,
        headers: dict[str, str] | None = None,
    ) -> Response:
        return Response(status_code=status, headers=headers)

    def view(
        self,
        name: str,
        data: dict[str, Any] | None = None,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> HTMLResponse:
        from almasix.prism.helpers import view

        return view(name, data, status=status, headers=headers)

    def redirect(
        self,
        to: str,
        *,
        status: int = 302,
        headers: dict[str, str] | None = None,
    ) -> Redirect:
        return redirect(to, status=status, headers=headers)

    def back(
        self,
        fallback: str = "/",
        *,
        status: int = 302,
        headers: dict[str, str] | None = None,
    ) -> Redirect:
        return back(fallback, status=status, headers=headers)

    def file(
        self,
        path: str | Path,
        *,
        headers: dict[str, str] | None = None,
        media_type: str | None = None,
    ) -> FileResponse:
        """Send a file inline — an image or PDF the browser should display."""
        return FileResponse(str(path), headers=headers, media_type=media_type)

    def download(
        self,
        path: str | Path,
        name: str | None = None,
        *,
        headers: dict[str, str] | None = None,
        media_type: str | None = None,
    ) -> FileResponse:
        """Send a file as an attachment, named ``name`` on the way out."""
        return FileResponse(
            str(path),
            filename=name or Path(path).name,
            headers=headers,
            media_type=media_type,
        )

    def stream(
        self,
        content: Iterable[Any] | AsyncIterable[Any],
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
        media_type: str | None = None,
    ) -> StreamingResponse:
        """Stream an iterable or async iterable as the response body."""
        return StreamingResponse(
            content,
            status_code=status,
            headers=headers,
            media_type=media_type,
        )

    def __call__(
        self,
        content: Any = None,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> StarletteResponse:
        return make_response(content, status=status, headers=headers)
