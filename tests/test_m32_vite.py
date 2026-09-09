"""M32 — `@vite`: dev server while it runs, the manifest once it has built.

The stacks the installer scaffolds are only real if a template can link what
they emit, so this holds both halves: the hot file, and the hashed files a
build names in its manifest.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from almasix.prism.engine import Engine
from almasix.prism.vite import (
    Vite,
    ViteEntryNotFound,
    ViteManifestNotFound,
    vite,
    vite_react_refresh,
)


@pytest.fixture()
def unbooted(monkeypatch: pytest.MonkeyPatch) -> None:
    """No application, so the root is the working directory.

    Another module's booted application would otherwise still be the current
    one, and its base path is not this test's `tmp_path`.
    """
    monkeypatch.setattr("almasix.framework.helpers._application", None)


MANIFEST = {
    "resources/css/app.css": {"file": "assets/app-1111.css", "isEntry": True},
    "resources/js/app.js": {
        "file": "assets/app-2222.js",
        "isEntry": True,
        "css": ["assets/app-1111.css"],
    },
}


@pytest.fixture()
def built(tmp_path: Path) -> Path:
    directory = tmp_path / "public" / "build" / ".vite"
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
    return tmp_path


def test_a_built_manifest_gives_hashed_tags(built: Path) -> None:
    tags = Vite(base_path=built).tag_list(["resources/css/app.css", "resources/js/app.js"])

    assert tags == [
        '<link rel="stylesheet" href="/build/assets/app-1111.css"/>',
        '<script type="module" src="/build/assets/app-2222.js"></script>',
    ]


def test_a_stylesheet_a_script_imports_is_linked_once(built: Path) -> None:
    tags = Vite(base_path=built).tag_list("resources/js/app.js")

    assert tags[0].startswith('<link rel="stylesheet"')
    assert len([tag for tag in tags if "app-1111.css" in tag]) == 1


def test_entry_urls_and_positional_entries(built: Path) -> None:
    engine = Vite(base_path=built)

    assert engine.entry_url("resources/js/app.js") == "/build/assets/app-2222.js"
    assert engine("resources/css/app.css", "resources/js/app.js").count("\n") == 1
    assert engine.has_manifest() is True


def test_a_manifest_that_does_not_name_the_entry_says_what_it_does(built: Path) -> None:
    with pytest.raises(ViteEntryNotFound, match="resources/js/other.js"):
        Vite(base_path=built).tag_list("resources/js/other.js")


def test_the_hot_file_points_everything_at_the_dev_server(built: Path) -> None:
    (built / "public" / "hot").write_text("http://127.0.0.1:5199/\n", encoding="utf-8")
    engine = Vite(base_path=built)

    tags = engine.tag_list(["resources/css/app.css", "resources/js/app.js"])

    assert tags[0] == '<script type="module" src="http://127.0.0.1:5199/@vite/client"></script>'
    assert '<link rel="stylesheet" href="http://127.0.0.1:5199/resources/css/app.css"/>' in tags
    assert '<script type="module" src="http://127.0.0.1:5199/resources/js/app.js"></script>' in tags
    assert engine.entry_url("resources/js/app.js") == "http://127.0.0.1:5199/resources/js/app.js"
    assert "@react-refresh" in engine.react_refresh()


def test_an_empty_hot_file_means_the_default_port(tmp_path: Path) -> None:
    (tmp_path / "public").mkdir()
    (tmp_path / "public" / "hot").write_text("", encoding="utf-8")

    assert Vite(base_path=tmp_path).dev_server_url() == "http://localhost:5173"


def test_react_refresh_is_silent_in_production(built: Path) -> None:
    assert Vite(base_path=built).react_refresh() == ""


def test_no_build_is_a_note_in_development(tmp_path: Path) -> None:
    tags = Vite(base_path=tmp_path).tag_list("resources/js/app.js")

    assert len(tags) == 1
    assert "npm run build" in tags[0]
    assert tags[0].startswith("<!--")


def test_no_build_is_an_error_when_debug_is_off(tmp_path: Path, monkeypatch) -> None:
    # `almasix.prism.vite` names the helper on the package, as
    # `almasix.routing.url` does, so the module is reached by import machinery.
    vite_module = importlib.import_module("almasix.prism.vite")

    monkeypatch.setattr(vite_module, "_debugging", lambda: False)

    with pytest.raises(ViteManifestNotFound, match="npm run build"):
        Vite(base_path=tmp_path).tag_list("resources/js/app.js")


def test_debugging_reads_the_application_when_there_is_one(monkeypatch) -> None:
    import almasix.config

    vite_module = importlib.import_module("almasix.prism.vite")

    monkeypatch.setattr(almasix.config, "config", lambda *_a, **_k: False)
    assert vite_module._debugging() is False
    monkeypatch.setattr(almasix.config, "config", lambda *_a, **_k: True)
    assert vite_module._debugging() is True


def test_a_manifest_beside_the_build_is_also_read(tmp_path: Path) -> None:
    build = tmp_path / "public" / "build"
    build.mkdir(parents=True)
    (build / "manifest.json").write_text(json.dumps(MANIFEST), encoding="utf-8")

    assert Vite(base_path=tmp_path).entry_url("resources/css/app.css") == (
        "/build/assets/app-1111.css"
    )


def test_a_manifest_that_is_not_an_object_reads_as_empty(tmp_path: Path) -> None:
    build = tmp_path / "public" / "build"
    build.mkdir(parents=True)
    (build / "manifest.json").write_text("[]", encoding="utf-8")

    assert Vite(base_path=tmp_path).manifest() == {}


def test_the_root_falls_back_to_the_working_directory(
    tmp_path: Path, monkeypatch, unbooted: None
) -> None:
    monkeypatch.chdir(tmp_path)

    assert Vite().hot_path() == tmp_path / "public" / "hot"


def test_the_root_is_the_booted_application(tmp_path: Path, monkeypatch) -> None:
    class FakeApplication:
        base_path = tmp_path / "app_root"

    monkeypatch.setattr(
        "almasix.framework.helpers.current_application",
        lambda: FakeApplication(),
    )

    assert Vite().hot_path() == tmp_path / "app_root" / "public" / "hot"


def test_the_directive_renders_through_the_engine(built: Path, monkeypatch, unbooted: None) -> None:
    monkeypatch.chdir(built)
    views = built / "resources" / "views"
    views.mkdir(parents=True)
    (views / "page.prism.html").write_text(
        "<head>@vite('resources/js/app.js')@viteReactRefresh</head>",
        encoding="utf-8",
    )

    html = Engine(paths=[views]).render("page", {})

    assert '<script type="module" src="/build/assets/app-2222.js"></script>' in html
    assert "&lt;" not in html  # tags are markup, not escaped text


def test_the_module_level_helpers_use_the_current_root(
    built: Path, monkeypatch, unbooted: None
) -> None:
    monkeypatch.chdir(built)

    assert "app-2222.js" in vite(["resources/js/app.js"])
    assert vite_react_refresh() == ""
