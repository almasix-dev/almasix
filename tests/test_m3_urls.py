"""M3 — URL generation honoring APP_URL and APP_BASE_PATH."""

from __future__ import annotations

import pytest

from almasix.config import ConfigRepository, set_repository
from almasix.http import redirect
from almasix.routing import UrlGenerator, asset, url


@pytest.fixture
def configured() -> ConfigRepository:
    repository = ConfigRepository()
    repository.set("app.url", "https://example.com")
    repository.set("app.base_path", "/apps/foo")
    set_repository(repository)
    return repository


def test_generator_applies_base_path() -> None:
    generator = UrlGenerator("https://example.com", "/apps/foo")

    assert generator.to("/") == "https://example.com/apps/foo"
    assert generator.to("/progress") == "https://example.com/apps/foo/progress"
    assert generator.to("api/health") == "https://example.com/apps/foo/api/health"
    assert generator.to("/progress", absolute=False) == "/apps/foo/progress"
    assert generator.asset("css/app.css") == "https://example.com/apps/foo/css/app.css"


def test_generator_normalizes_and_passes_through_absolute_urls() -> None:
    # Trailing/leading slashes in config must not produce doubled separators.
    generator = UrlGenerator("https://example.com/", "apps/foo/")
    assert generator.to("/x") == "https://example.com/apps/foo/x"

    rootless = UrlGenerator("", "")
    assert rootless.to("/x") == "/x"
    assert rootless.to("/") == "/"
    assert rootless.to("") == "/"

    for external in ("https://cdn.example.com/a.css", "//cdn.example.com/a.css"):
        assert generator.to(external) == external


def test_helpers_read_config(configured: ConfigRepository) -> None:
    assert url("/progress") == "https://example.com/apps/foo/progress"
    assert url("/progress", absolute=False) == "/apps/foo/progress"
    assert asset("css/app.css", absolute=False) == "/apps/foo/css/app.css"

    configured.set("app.base_path", "")
    assert url("/progress") == "https://example.com/progress"


def test_redirect_honors_base_path(configured: ConfigRepository) -> None:
    response = redirect("/progress")
    assert response.status_code == 302
    assert response.headers["location"] == "/apps/foo/progress"

    permanent = redirect("/progress", status=301)
    assert permanent.status_code == 301
