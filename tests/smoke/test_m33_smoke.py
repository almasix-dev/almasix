"""M33 smoke — the routing demo, the docs, and the board."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke]

PROGRESS = Path(__file__).resolve().parents[2] / "examples" / "progress"
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def progress_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    module = importlib.import_module("bootstrap.app")
    return TestClient(module.asgi)


def test_m33_demo_command_exercises_the_routing_surface() -> None:
    result = subprocess.run(
        [sys.executable, "smith", "progress:routing"],
        cwd=PROGRESS,
        capture_output=True,
        text=True,
        check=False,
    )
    out = result.stdout + result.stderr

    assert result.returncode == 0, out

    for line in (
        # Verbs and the shapes that need no controller.
        "get answers      -> GET|HEAD",
        "any answers      -> 7 verbs",
        "redirect status  -> 302 / 301",
        "/{fallback_placeholder:path}",
        # Constraints, including the optional parameter's two compiled paths.
        "where_number     -> {'id': '[0-9]+'}",
        "where_in         -> s|m|l",
        "global pattern   -> {'account': '[0-9]+'}",
        "optional {name?}  -> ['/greet/{name}', '/greet']",
        # Groups merge prefix, name, middleware, domain, and controller.
        "/admin/trash/photos        admin.trash    ['auth', 'can:restore']",
        "domain           -> {account}.almasix.test",
        "controller       -> PhotoController@index",
        # Resource routing.
        "resource         -> 7 routes",
        "/photos/{photo}/edit               photos.edit",
        "nested           -> ['/photos/{photo}/comments', "
        "'/photos/{photo}/comments/{comment}']",
        "shallow          -> ['/photos/{photo}/comments', '/comments/{comment}']",
        "shallow names    -> ['photos.comments.index', 'comments.show']",
        "scoped           -> /photos/{photo}/comments/{comment:slug}",
        "a slash prefixes -> /api/tags named tags.index",
        "localized verbs  -> ['/fotos/crear', '/fotos/{foto}/editar']",
        # Singletons: no index, no id.
        "/profile                           profile.show",
        "DELETE           /settings                          settings.destroy",
        # Binding.
        "route key        -> Article.slug",
        "binding field    -> {'post': 'slug'}",
        "Route.model      -> ['article']",
        # URL generation: every parameter shape reaches the same URL.
        "a scalar         -> http://127.0.0.1:3000/greet/ada",
        "a mapping        -> http://127.0.0.1:3000/greet/ada",
        "a keyword        -> http://127.0.0.1:3000/greet/ada",
        "a model          -> http://127.0.0.1:3000/greet/ada",
        "leftovers query  -> http://127.0.0.1:3000/photos?page=2",
        "relative         -> /greet/ada",
        # Signed URLs.
        "signed_route     -> valid=True",
        "edited           -> valid=False",
        "expired          -> valid=False",
        "expired, ignored -> valid=True",
        # Defaults fill a named parameter and never spill into the query.
        "default filled   -> http://127.0.0.1:3000/en/help",
        "explicit wins    -> http://127.0.0.1:3000/fr/help",
        "no query spill   -> http://127.0.0.1:3000/photos",
        "routing demo ok",
    ):
        assert line in out, line


def test_m33_route_list_reports_names_and_middleware() -> None:
    result = subprocess.run(
        [sys.executable, "smith", "route:list", "--middleware", "--sort=name"],
        cwd=PROGRESS,
        capture_output=True,
        text=True,
        check=False,
    )
    out = result.stdout + result.stderr

    assert result.returncode == 0, out
    assert "Name" in out
    assert "Middleware" in out
    assert "GET|HEAD" in out


def test_m33_docs_cover_routing_and_url_generation() -> None:
    docs = ROOT / "website" / "src" / "content" / "docs"

    routing = (docs / "routing.md").read_text(encoding="utf-8")
    for topic in (
        "fallback",
        "where_number",
        "api_resource",
        "shallow",
        "scoped",
        "singleton",
        "with_trashed",
        "missing",
        "_method",
        "domain",
        "route:list",
    ):
        assert topic in routing, topic

    urls = (docs / "urls.md").read_text(encoding="utf-8")
    for topic in (
        "route(",
        "signed_route",
        "temporary_signed_route",
        "has_valid_signature",
        "to_route",
        "action(",
        "defaults",
        "force_scheme",
        "previous",
    ):
        assert topic in urls, topic


def test_m33_board_marks_routing_complete(progress_client: TestClient) -> None:
    board = progress_client.get("/api/progress").json()
    by_id = {milestone["id"]: milestone for milestone in board["milestones"]}

    assert by_id["M33"]["status"] == "complete"
    assert "smith progress:routing" in by_id["M33"]["proof"]


def test_m33_readme_points_at_the_demo() -> None:
    readme = (PROGRESS / "README.md").read_text(encoding="utf-8")

    assert "| **M33** | `smith progress:routing`" in readme
    assert "\nsmith progress:routing\n" in readme
