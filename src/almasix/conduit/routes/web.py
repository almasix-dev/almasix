"""Conduit HTTP routes — signed update endpoint + client asset + uploads."""

from __future__ import annotations

from pathlib import Path

from starlette.responses import FileResponse, JSONResponse, Response

from almasix.conduit.mechanism import handle_update
from almasix.conduit.uploads import store_upload
from almasix.http.request import Request
from almasix.routing import Route

_JS = Path(__file__).resolve().parent.parent / "resources" / "js" / "conduit.js"


async def conduit_update(request: Request) -> Response:
    return await handle_update(request)


def conduit_script() -> Response:
    if not _JS.is_file():
        return Response(
            "// conduit.js missing\n", media_type="application/javascript", status_code=404
        )
    return FileResponse(_JS, media_type="application/javascript")


async def conduit_upload(request: Request) -> Response:
    """Temporary file upload for ``wire:model`` file inputs."""
    files = request.files() if hasattr(request, "files") else {}
    if callable(files):
        files = files()
    uploaded = None
    if isinstance(files, dict):
        uploaded = files.get("file") or next(iter(files.values()), None)
    if uploaded is None:
        return JSONResponse({"message": "No file"}, status_code=422)
    path = store_upload(uploaded)
    return JSONResponse({"path": path})


with Route.group(middleware=["web"]):
    # Every update must present a valid relative signature (see conduit.signing).
    Route.post("/conduit/update", conduit_update, middleware=["signed:relative"])
    Route.post("/conduit/upload", conduit_upload)
    Route.get("/conduit/conduit.js", conduit_script)
    # Rename-window aliases (also signed)
    Route.post("/flux/update", conduit_update, middleware=["signed:relative"])
    Route.get("/flux/flux.js", conduit_script)
