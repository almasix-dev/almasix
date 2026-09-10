"""M29 — Package development: ServiceProvider helpers, discovery, make:package."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from almasix.orm.migration import (
    forget_migration_paths,
    package_migration_paths,
    register_migration_paths,
)
from almasix.prism.engine import Engine, ViewNotFoundError
from almasix.providers.package_manifest import PackageManifest
from almasix.providers.provider import ServiceProvider
from almasix.smith.make import MakeError, make_package


@pytest.fixture(autouse=True)
def clean_publishes() -> Any:
    ServiceProvider.forget_publishes()
    forget_migration_paths()
    yield
    ServiceProvider.forget_publishes()
    forget_migration_paths()


@pytest.fixture
def app(tmp_path: Path) -> Any:
    from almasix.framework.application import Application

    return Application(tmp_path)


def test_merge_config_from_sets_defaults_when_missing(app: Any, tmp_path: Path) -> None:
    cfg = tmp_path / "pkg.py"
    cfg.write_text("config = {'driver': 'pigeon', 'from': 'a@b.c'}\n", encoding="utf-8")

    class Pkg(ServiceProvider):
        def register(self) -> None:
            self.merge_config_from(cfg, "courier")

    Pkg(app).register()
    assert app.config.get("courier.driver") == "pigeon"
    assert app.config.get("courier.from") == "a@b.c"


def test_merge_config_from_lets_app_values_win(app: Any, tmp_path: Path) -> None:
    cfg = tmp_path / "pkg.py"
    cfg.write_text("config = {'driver': 'pigeon', 'retries': 3}\n", encoding="utf-8")
    app.config.set("courier", {"driver": "hawk"})

    class Pkg(ServiceProvider):
        def register(self) -> None:
            self.merge_config_from(cfg, "courier")

    Pkg(app).register()
    assert app.config.get("courier.driver") == "hawk"
    assert app.config.get("courier.retries") == 3


def test_load_routes_from_executes_the_file(app: Any, tmp_path: Path) -> None:
    routes = tmp_path / "web.py"
    routes.write_text(
        "from almasix.routing import Route\n"
        "def home():\n"
        "    return {'ok': True}\n"
        "Route.get('/pkg', home)\n",
        encoding="utf-8",
    )
    from almasix.routing.router import set_router

    set_router(app.router)

    class Pkg(ServiceProvider):
        def boot(self) -> None:
            self.load_routes_from(routes)

    Pkg(app).boot()
    assert any(route.uri == "/pkg" for route in app.router.routes)


def test_load_views_from_registers_namespace_and_publish_tag(
    app: Any, tmp_path: Path
) -> None:
    views = tmp_path / "views"
    views.mkdir()
    (views / "welcome.prism.html").write_text("<p>hi</p>", encoding="utf-8")
    engine = Engine(paths=[app.path("resources", "views")])
    app.container.instance(Engine, engine)

    class Pkg(ServiceProvider):
        def boot(self) -> None:
            self.load_views_from(views, "courier")

    Pkg(app).boot()
    assert engine.find("courier::welcome").is_file()
    assert "courier-views" in ServiceProvider.publishable_tags()


def test_namespaced_view_prefers_vendor_override(tmp_path: Path) -> None:
    hint = tmp_path / "pkg" / "views"
    hint.mkdir(parents=True)
    (hint / "mail.prism.html").write_text("<p>package</p>", encoding="utf-8")
    app_views = tmp_path / "resources" / "views"
    vendor = app_views / "vendor" / "courier"
    vendor.mkdir(parents=True)
    (vendor / "mail.prism.html").write_text("<p>override</p>", encoding="utf-8")

    engine = Engine(paths=[app_views])
    engine.add_namespace("courier", hint)
    assert engine.find("courier::mail").read_text(encoding="utf-8") == "<p>override</p>"
    assert engine.exists("courier::mail") is True
    assert engine.exists("courier::missing") is False


def test_namespaced_view_missing_raises(tmp_path: Path) -> None:
    engine = Engine(paths=[tmp_path])
    with pytest.raises(ViewNotFoundError):
        engine.find("courier::gone")
    with pytest.raises(ViewNotFoundError):
        engine.find("::bad")


def test_load_migrations_from_registers_paths(tmp_path: Path) -> None:
    path = tmp_path / "migrations"
    path.mkdir()
    register_migration_paths(path)
    register_migration_paths([path])  # idempotent
    assert package_migration_paths() == [path.resolve()]


def test_load_translations_from_adds_namespace(app: Any, tmp_path: Path) -> None:
    lang = tmp_path / "lang"
    (lang / "en").mkdir(parents=True)
    (lang / "en" / "messages.py").write_text(
        "translations = {'greeting': 'Hello'}\n", encoding="utf-8"
    )
    from almasix.translation.helpers import Lang, set_translator
    from almasix.translation.translator import Translator

    translator = Translator(locale="en", fallback="en")
    set_translator(translator)

    class Pkg(ServiceProvider):
        def boot(self) -> None:
            self.load_translations_from(lang, "courier")

    Pkg(app).boot()
    assert Lang.get("courier::messages.greeting") == "Hello"


def test_publishes_migrations_marks_sources_for_timestamp_rewrite(
    app: Any, tmp_path: Path
) -> None:
    source = tmp_path / "0001_01_01_000000_create_courier_table.py"
    source.write_text("# mig\n", encoding="utf-8")

    class Pkg(ServiceProvider):
        def boot(self) -> None:
            self.publishes_migrations(
                {source: "database/migrations/create_courier_table.py"},
                "courier-migrations",
            )

    Pkg(app).boot()
    assert ServiceProvider.is_migration_publish(source)
    dest = ServiceProvider.migration_publish_destination(
        source, Path("database/migrations/create_courier_table.py")
    )
    assert dest.name.endswith("_create_courier_table.py")
    assert dest.name[:8].isdigit() or "_" in dest.name[:11]


def test_commands_registers_on_console_kernel(app: Any) -> None:
    from almasix.console.command import Command
    from almasix.console.kernel import ConsoleKernel

    class DemoCommand(Command):
        signature = "demo:pkg"
        description = "demo"

        def handle(self) -> int:
            return self.SUCCESS

    kernel = ConsoleKernel(app)
    app.container.instance(ConsoleKernel, kernel)

    class Pkg(ServiceProvider):
        def boot(self) -> None:
            self.commands([DemoCommand])

    Pkg(app).boot()
    assert "demo:pkg" in kernel.commands


def test_package_manifest_reads_entry_points(monkeypatch: pytest.MonkeyPatch) -> None:
    ep = MagicMock()
    ep.value = "courier.provider:CourierServiceProvider"
    ep.dist = MagicMock()
    ep.dist.name = "almasix-courier"

    monkeypatch.setattr(
        "almasix.providers.package_manifest.importlib.metadata.entry_points",
        lambda group=None: [ep] if group == "almasix.providers" else [],
    )
    assert PackageManifest().providers() == ["courier.provider.CourierServiceProvider"]
    assert PackageManifest().providers(dont_discover=["almasix-courier"]) == []


def test_package_manifest_accepts_dotted_value(monkeypatch: pytest.MonkeyPatch) -> None:
    ep = MagicMock()
    ep.value = "pkg.provider.PkgServiceProvider"
    ep.dist = None

    monkeypatch.setattr(
        "almasix.providers.package_manifest.importlib.metadata.entry_points",
        lambda group=None: [ep],
    )
    assert PackageManifest().providers() == ["pkg.provider.PkgServiceProvider"]


def test_register_configured_providers_discovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from almasix.framework.application import Application

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        "config = {'providers': [], 'skip_provider_discovery': False, 'dont_discover': []}\n",
        encoding="utf-8",
    )
    app = Application(tmp_path)
    app.load_configuration()

    class Discovered(ServiceProvider):
        hit = False

        def register(self) -> None:
            Discovered.hit = True

    monkeypatch.setattr(
        "almasix.providers.package_manifest.PackageManifest.providers",
        lambda self, dont_discover=None: ["x.Discovered"],
    )
    monkeypatch.setattr(app, "_import_provider", lambda path: Discovered)
    Discovered.hit = False
    app.register_configured_providers()
    assert Discovered.hit is True


def test_register_configured_providers_honours_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from almasix.framework.application import Application

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        "config = {'providers': [], 'skip_provider_discovery': True}\n",
        encoding="utf-8",
    )
    app = Application(tmp_path)
    app.load_configuration()

    class Discovered(ServiceProvider):
        hit = False

        def register(self) -> None:
            Discovered.hit = True

    monkeypatch.setattr(
        "almasix.providers.package_manifest.PackageManifest.providers",
        lambda self, dont_discover=None: ["x.Discovered"],
    )
    monkeypatch.setattr(app, "_import_provider", lambda path: Discovered)
    Discovered.hit = False
    app.register_configured_providers()
    assert Discovered.hit is False


def test_register_configured_providers_swallows_broken_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from almasix.framework.application import Application

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        "config = {'providers': [], 'skip_provider_discovery': False}\n",
        encoding="utf-8",
    )
    app = Application(tmp_path)
    app.load_configuration()

    def boom(path: str) -> type[ServiceProvider]:
        raise ImportError("nope")

    monkeypatch.setattr(
        "almasix.providers.package_manifest.PackageManifest.providers",
        lambda self, dont_discover=None: ["broken.Provider"],
    )
    monkeypatch.setattr(app, "_import_provider", boom)
    app.register_configured_providers()  # must not raise


def test_make_package_scaffolds_tree(tmp_path: Path) -> None:
    root = make_package("courier", base_path=tmp_path)
    assert (root / "pyproject.toml").is_file()
    assert 'almasix.providers"' in (root / "pyproject.toml").read_text(encoding="utf-8")
    assert (root / "src" / "courier" / "provider.py").is_file()
    assert (root / "src" / "courier" / "config" / "courier.py").is_file()
    assert (root / "src" / "courier" / "routes" / "web.py").is_file()
    assert (root / "src" / "courier" / "resources" / "views" / "welcome.prism.html").is_file()
    assert (root / "src" / "courier" / "lang" / "en" / "messages.py").is_file()
    assert "CourierServiceProvider" in (root / "src" / "courier" / "provider.py").read_text()


def test_make_package_refuses_existing_without_force(tmp_path: Path) -> None:
    make_package("acme", base_path=tmp_path)
    with pytest.raises(MakeError, match="already exists"):
        make_package("acme", base_path=tmp_path)


def test_make_package_rejects_empty_name(tmp_path: Path) -> None:
    with pytest.raises(MakeError, match="required"):
        make_package("  ", base_path=tmp_path)


def test_vendor_publish_rewrites_migration_timestamp(
    app: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from almasix.console.commands.vendor import VendorPublishCommand

    source = tmp_path / "pkg" / "0001_01_01_000000_create_widgets_table.py"
    source.parent.mkdir(parents=True)
    source.write_text("# migration\n", encoding="utf-8")

    class Pkg(ServiceProvider):
        def boot(self) -> None:
            self.publishes_migrations(
                {source: app.path("database", "migrations", "create_widgets_table.py")},
                "widgets-migrations",
            )

    Pkg(app).boot()
    code = VendorPublishCommand(app).run(None, {"tag": ["widgets-migrations"]})
    assert code == 0
    published = list((app.path("database", "migrations")).glob("*_create_widgets_table.py"))
    assert len(published) == 1
    assert published[0].read_text(encoding="utf-8") == "# migration\n"
    assert "Published" in capsys.readouterr().out


def test_merge_config_from_non_dict_defaults_and_existing(app: Any, tmp_path: Path) -> None:
    cfg = tmp_path / "odd.py"
    cfg.write_text("VALUE = 1\n", encoding="utf-8")  # no config= → dict of names
    class Pkg(ServiceProvider):
        def register(self) -> None:
            self.merge_config_from(cfg, "odd")

    Pkg(app).register()
    assert app.config.get("odd.VALUE") == 1

    # Non-dict existing is left alone.
    app.config.set("scalar", "keep")
    cfg2 = tmp_path / "scalar.py"
    cfg2.write_text("config = {'a': 1}\n", encoding="utf-8")

    class Pkg2(ServiceProvider):
        def register(self) -> None:
            self.merge_config_from(cfg2, "scalar")

    Pkg2(app).register()
    assert app.config.get("scalar") == "keep"


def test_merge_config_from_non_dict_module_result(app: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "x.py"
    cfg.write_text("config = 'not-a-dict'\n", encoding="utf-8")

    class Pkg(ServiceProvider):
        def register(self) -> None:
            self.merge_config_from(cfg, "x")

    Pkg(app).register()
    assert app.config.get("x") == {}


def test_load_views_from_without_engine_still_publishes(app: Any, tmp_path: Path) -> None:
    views = tmp_path / "views"
    views.mkdir()

    class Pkg(ServiceProvider):
        def boot(self) -> None:
            self.load_views_from(views, "acme")

    Pkg(app).boot()
    assert "acme-views" in ServiceProvider.publishable_tags()


def test_load_views_from_file_hint_skips_publish(app: Any, tmp_path: Path) -> None:
    file_hint = tmp_path / "one.prism.html"
    file_hint.write_text("<p/>", encoding="utf-8")

    class Pkg(ServiceProvider):
        def boot(self) -> None:
            self.load_views_from(file_hint, "solo")

    Pkg(app).boot()
    assert "solo-views" not in ServiceProvider.publishable_tags()


def test_migration_destination_falls_back_to_source_slug() -> None:
    source = Path("/pkg/0001_01_01_000000_create_widgets_table.py")
    # No extension → slug equals destination.name → fall back to the source stamp slug.
    dest = Path("database/migrations") / "create_widgets_table"
    out = ServiceProvider.migration_publish_destination(source, dest)
    assert out.name.endswith("_create_widgets_table.py")


def test_package_manifest_skips_empty_entry_points(monkeypatch: pytest.MonkeyPatch) -> None:
    empty = MagicMock()
    empty.value = ""
    empty.dist = None
    bad_colon = MagicMock()
    bad_colon.value = ":OnlyClass"
    bad_colon.dist = None
    monkeypatch.setattr(
        "almasix.providers.package_manifest.importlib.metadata.entry_points",
        lambda group=None: [empty, bad_colon],
    )
    assert PackageManifest().providers() == []


def test_make_package_force_and_custom_path(tmp_path: Path) -> None:
    root = make_package("demo", base_path=tmp_path, path=tmp_path / "custom" / "demo")
    assert root == tmp_path / "custom" / "demo"
    make_package("demo", base_path=tmp_path, path=tmp_path / "custom" / "demo", force=True)
    with pytest.raises(MakeError, match="Invalid"):
        make_package("123-bad", base_path=tmp_path)


def test_paths_to_publish_variants(app: Any, tmp_path: Path) -> None:
    src = tmp_path / "a.py"
    src.write_text("x=1\n", encoding="utf-8")
    dest = app.path("config", "a.py")

    class Pkg(ServiceProvider):
        def boot(self) -> None:
            self.publishes({src: dest}, "a-config")

    Pkg(app).boot()
    assert ServiceProvider.publishable_providers()
    assert ServiceProvider.paths_to_publish() == {src: dest}
    assert ServiceProvider.paths_to_publish(provider=Pkg.provider_name(), tag="a-config") == {
        src: dest
    }
    assert ServiceProvider.paths_to_publish(provider=Pkg.provider_name(), tag="nope") == {}


def test_load_migrations_from_on_provider(app: Any, tmp_path: Path) -> None:
    path = tmp_path / "migrations"
    path.mkdir()

    class Pkg(ServiceProvider):
        def boot(self) -> None:
            self.load_migrations_from(path)

    Pkg(app).boot()
    assert path.resolve() in package_migration_paths()


def test_load_config_file_raises_when_unreadable(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.util as util

    monkeypatch.setattr(util, "spec_from_file_location", lambda *a, **k: None)
    with pytest.raises(ImportError, match="Cannot load config"):
        ServiceProvider._load_config_file(Path("/nope.py"))


def test_commands_soft_fails_without_kernel(app: Any) -> None:
    from almasix.console.command import Command

    class Demo(Command):
        signature = "demo:soft"
        description = "x"

        def handle(self) -> int:
            return self.SUCCESS

    class Pkg(ServiceProvider):
        def boot(self) -> None:
            self.commands([Demo])

    Pkg(app).boot()  # no ConsoleKernel bound — soft success


def test_engine_cache_views_includes_namespaced(tmp_path: Path) -> None:
    hint = tmp_path / "pkg"
    hint.mkdir()
    (hint / "hi.prism.html").write_text("<p>x</p>", encoding="utf-8")
    engine = Engine(paths=[tmp_path / "empty"], cache_enabled=True)
    (tmp_path / "empty").mkdir()
    engine.add_namespace("pkg", hint)
    assert engine.cache_views() >= 1
