"""M8 smoke — Handler polarity, status mapping, unmatched routes, logging."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke, pytest.mark.regression]

PROGRESS = Path(__file__).resolve().parents[2] / "examples" / "progress"


@pytest.fixture()
def progress_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    monkeypatch.setenv("APP_DEBUG", "false")
    monkeypatch.setenv("LOG_CHANNEL", "null")
    module = importlib.import_module("bootstrap.app")
    # Rebuild ASGI after env so APP_DEBUG=false sticks if config already loaded.
    app = module.application
    app.config.set("app.debug", False)
    app.config.set("logging.default", "null")
    app._asgi = None
    module.asgi = app.asgi
    return TestClient(module.asgi, raise_server_exceptions=False)


def test_m8_web_boom_html_production(progress_client: TestClient) -> None:
    response = progress_client.get("/boom")
    assert response.status_code == 500
    assert "text/html" in response.headers["content-type"]
    assert "Almasix debug page" not in response.text
    assert "500" in response.text


def test_m8_api_explode_json_envelope(progress_client: TestClient) -> None:
    response = progress_client.get("/api/explode")
    assert response.status_code == 500
    assert response.json() == {
        "message": "Server Error",
        "status": 500,
        "errors": {},
    }


def test_m8_accept_json_on_web_still_html(progress_client: TestClient) -> None:
    response = progress_client.get(
        "/boom",
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 500
    assert "text/html" in response.headers["content-type"]


def test_m8_unmatched_web_html_vs_api_json(progress_client: TestClient) -> None:
    web = progress_client.get("/no-such-page-m8")
    assert web.status_code == 404
    assert "text/html" in web.headers["content-type"]
    assert "404" in web.text

    api = progress_client.get("/api/no-such-resource-m8")
    assert api.status_code == 404
    body = api.json()
    assert body["status"] == 404
    assert "message" in body
    assert "errors" in body


def test_m8_errors_publish_and_log_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from almasix.exceptions import publish_errors
    from almasix.log import log
    from almasix.smith.cli import app as smith_app

    dest = publish_errors(tmp_path, bundle="default")
    assert (dest / "500.prism.html").is_file()

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(smith_app, ["errors:publish", "--bundle", "tailwind", "--force"])
    assert result.exit_code == 0

    # Context helper must not raise when no manager is installed.
    log().with_(request_id="m8").info("smoke-context")
