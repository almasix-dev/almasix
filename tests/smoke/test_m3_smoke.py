"""M3 smoke — validation, generators, and subpath-safe URLs."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from almasix.installer.scaffold import scaffold_app
from almasix.smith.cli import app as smith_app
from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke, pytest.mark.regression]

runner = CliRunner()


def test_m3_s1_make_commands_scaffold_into_a_generated_app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = scaffold_app("m3_make", destination=tmp_path / "m3_make")
    # Generators write relative to the app root, like `php artisan make:*`.
    monkeypatch.chdir(root)

    for command, name, relative in (
        ("make:controller", "PostController", "app/http/controllers/post_controller.py"),
        ("make:request", "StorePostRequest", "app/http/requests/store_post_request.py"),
        ("make:middleware", "EnsureToken", "app/http/middleware/ensure_token.py"),
        ("make:provider", "BillingServiceProvider", "app/providers/billing_service_provider.py"),
    ):
        result = runner.invoke(smith_app, [command, name], catch_exceptions=False)
        assert result.exit_code == 0, result.stdout
        assert (root / relative).is_file()


def test_m3_s2_form_request_validates_before_the_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = scaffold_app("m3_validate", destination=tmp_path / "m3_validate")
    purge_generated_app_modules()
    monkeypatch.chdir(root)
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.delenv("APP_NAME", raising=False)

    (root / "app" / "http" / "requests").mkdir(parents=True, exist_ok=True)
    (root / "app" / "http" / "requests" / "__init__.py").write_text("", encoding="utf-8")
    (root / "app" / "http" / "requests" / "store_user_request.py").write_text(
        "from almasix.validation import Field, FormRequest\n"
        "\n"
        "class StoreUserRequest(FormRequest):\n"
        "    name: str = Field(min_length=2)\n"
        "    age: int = Field(default=18, ge=18)\n",
        encoding="utf-8",
    )
    (root / "app" / "http" / "controllers" / "user_controller.py").write_text(
        "from app.http.requests.store_user_request import StoreUserRequest\n"
        "from almasix.http import Controller\n"
        "\n"
        "class UserController(Controller):\n"
        "    async def store(self, request: StoreUserRequest) -> dict:\n"
        "        return {'created': request.validated()}\n",
        encoding="utf-8",
    )
    (root / "routes" / "api.py").write_text(
        '"""API routes."""\n'
        "from app.http.controllers.user_controller import UserController\n"
        "from almasix.routing import Route\n"
        "\n"
        'with Route.group(prefix="/api", middleware=["api"]):\n'
        '    Route.post("/users", [UserController, "store"])\n',
        encoding="utf-8",
    )

    try:
        module = importlib.import_module("bootstrap.app")
        client = TestClient(module.asgi, raise_server_exceptions=False)

        created = client.post("/api/users", json={"name": "Ada", "age": "30"})
        assert created.status_code == 200
        assert created.json() == {"created": {"name": "Ada", "age": 30}}

        invalid = client.post("/api/users", json={"age": 12})
        assert invalid.status_code == 422
        assert invalid.headers["content-type"].startswith("application/json")
        assert invalid.json() == {
            "message": "The given data was invalid.",
            "status": 422,
            "errors": {
                "name": ["The name field is required."],
                "age": ["The age must be at least 18."],
            },
        }
    finally:
        purge_generated_app_modules()


def test_m3_s3_generated_app_links_honor_base_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = scaffold_app("m3_subpath", destination=tmp_path / "m3_subpath")
    purge_generated_app_modules()
    monkeypatch.chdir(root)
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.delenv("APP_NAME", raising=False)

    env_file = root / ".env"
    env_file.write_text(
        env_file.read_text(encoding="utf-8").replace("APP_BASE_PATH=", "APP_BASE_PATH=/apps/m3"),
        encoding="utf-8",
    )
    # Process env wins over .env — pin the prefix for this smoke explicitly.
    monkeypatch.setenv("APP_BASE_PATH", "/apps/m3")

    try:
        module = importlib.import_module("bootstrap.app")
        client = TestClient(module.asgi)
        # Site root redirects into the mount; the app itself lives under the prefix.
        root_hit = client.get("/", follow_redirects=False)
        assert root_hit.status_code == 307
        assert root_hit.headers["location"] == "/apps/m3/"

        page = client.get("/apps/m3/")
        assert page.status_code == 200
        # Links must carry the public prefix, never a root-absolute path.
        assert 'href="/apps/m3/api/health"' in page.text
        assert 'href="/api/health"' not in page.text

        health = client.get("/apps/m3/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        assert client.get("/api/health").status_code == 404
    finally:
        purge_generated_app_modules()


def test_m3_s4_progress_example_validation_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(__file__).resolve().parents[2] / "examples" / "progress"
    purge_generated_app_modules()
    monkeypatch.chdir(root)
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.delenv("APP_NAME", raising=False)
    without_base_path(monkeypatch)
    try:
        module = importlib.import_module("bootstrap.app")
        client = TestClient(module.asgi, raise_server_exceptions=False)

        ok = client.post("/api/items", json={"name": "almasix", "count": "3", "flag": "true"})
        assert ok.status_code == 200
        assert ok.json()["validated"] == {
            "name": "almasix",
            "count": 3,
            "flag": True,
            "tags": [],
            "note": None,
        }

        inline = client.post(
            "/api/items/inline",
            json={"name": "almasix", "count": "3", "flag": "true"},
        )
        assert inline.status_code == 200
        assert inline.json()["via"] == "request.validate"
        assert inline.json()["validated"]["name"] == "almasix"

        invalid = client.post("/api/items", json={"name": "a", "count": 0, "tags": "nope"})
        assert invalid.status_code == 422
        assert invalid.json()["errors"] == {
            "name": ["The name must be at least 2 characters."],
            # attributes() renames the field, messages() overrides the rule text.
            "count": ["The item count must be at least 1."],
            "tags": ["The tags must be a list of strings."],
        }

        denied = client.post(
            "/api/items",
            json={"name": "almasix"},
            headers={"x-demo-forbid": "1"},
        )
        assert denied.status_code == 403
        assert denied.json() == {
            "message": "This action is unauthorized.",
            "status": 403,
            "errors": {},
        }
    finally:
        purge_generated_app_modules()
